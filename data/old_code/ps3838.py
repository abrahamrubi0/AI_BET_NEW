import os 
import time
import re
import sys
import json
import logging
import base64
from typing import Dict, List, Optional, Any, Tuple
import requests
from requests.auth import HTTPBasicAuth
from dotenv import dotenv_values

config = dotenv_values(".env")

# ===================== CONFIGURACIÓN DE LOGGING =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ps3838_tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== CONSTANTES =====================
# Nombres de archivos
JSON_INPUT_FILE = "bets_today.json"
SPORTS_JSON_FILE = "sports_ps3838.json"
GAME_IDS_CACHE_FILE = "game_ids_cache.json"
SETTLED_LAST_FILE = "settled_last.json"  # Archivo para guardar el valor 'last'

# Deportes por defecto si no se puede cargar el archivo
DEFAULT_SPORTS_MAPPING = {"Basketball": 4}

# Mapeo de nombres de ligas
LEAGUE_MAPPING = {
    "NCAAB": "NCAA"
}

# Ligas NCAA para comparaciones flexibles
NCAA_LEAGUES = ["NCAAB", "NCAA BASKETBALL", "NCAA", "NCAA FOOTBALL", "NCAAF"]

# URLs base para las APIs
API_BASE_URL = "https://api.ps3838.com/v3"
FIXTURES_API_PATH = f"{API_BASE_URL}/fixtures"
SETTLED_API_PATH = f"{API_BASE_URL}/fixtures/settled"

# ===================== VARIABLES GLOBALES =====================
# Estas variables se inicializarán en main()
last_game_ids = {}  # Formato: {'team1_team2': game_id}
active_bets = {}
processed_bets = set()
SPORTS_MAPPING = {}
settled_last_values = {}  # Diccionario para almacenar el último valor 'last' por sport_id

# Diccionarios de normalización de equipos
nba_teams = {}
teams_imported = False

# Credenciales
username = ""
password = ""
TELEGRAM_CHAT_ID = ""
TELEGRAM_BOT_TOKEN = ""

# ===================== INICIALIZACIÓN Y CARGA DE CONFIGURACIÓN =====================
def initialize_environment() -> bool:
    """
    Inicializa el entorno cargando variables necesarias y verificando dependencias.
    
    Returns:
        bool: True si la inicialización fue exitosa, False en caso contrario.
    """
    global teams_imported, nba_teams, username, password, TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN
    
    # Intentar importar diccionarios de equipos
    try:
        from teams import nba_teams
        teams_imported = True
        logger.info(f"Diccionario de equipos importado correctamente: {len(nba_teams)} equipos NBA disponibles")
    except ImportError:
        teams_imported = False
        nba_teams = {}
        logger.warning("No se pudo importar teams.py. Se usarán valores predeterminados.")
    
    # Cargar variables de entorno desde el fichero .env
    try:
        TELEGRAM_CHAT_ID = config['TELEGRAM_CHAT_ID']
        TELEGRAM_BOT_TOKEN = config['TELEGRAM_BOT_TOKEN']
        username = config['USERNAME']
        password = config['PASSWORD']
        
        # Verificar variables críticas
        if not all([TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, username, password]):
            logger.error("Faltan variables de entorno necesarias. Por favor verifica tu archivo .env")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error al cargar variables de entorno: {e}")
        return False

def load_game_ids() -> Dict[str, str]:
    """
    Carga los IDs de juegos guardados desde el archivo JSON.
    
    Returns:
        Dict[str, str]: Diccionario con los IDs de juegos cargados.
    """
    try:
        if os.path.exists(GAME_IDS_CACHE_FILE):
            with open(GAME_IDS_CACHE_FILE, 'r') as f:
                data = json.load(f)
                logger.info(f"Cargados {len(data)} IDs de juegos desde el archivo de caché")
                return data
        return {}
    except Exception as e:
        logger.error(f"Error cargando IDs de juegos: {e}")
        return {}

def save_game_ids(game_ids: Dict[str, str]) -> None:
    """
    Guarda los IDs de juegos en el archivo JSON.
    
    Args:
        game_ids (Dict[str, str]): Diccionario con los IDs de juegos a guardar.
    """
    try:
        with open(GAME_IDS_CACHE_FILE, 'w') as f:
            json.dump(game_ids, f)
        logger.info(f"Guardados {len(game_ids)} IDs de juegos en el archivo de caché")
    except Exception as e:
        logger.error(f"Error guardando IDs de juegos: {e}")

def load_settled_last_values() -> Dict[str, int]:
    """
    Carga los valores 'last' para cada sport_id desde el archivo JSON.
    
    Returns:
        Dict[str, int]: Diccionario con los valores 'last' por sport_id.
    """
    try:
        if os.path.exists(SETTLED_LAST_FILE):
            with open(SETTLED_LAST_FILE, 'r') as f:
                data = json.load(f)
                logger.info(f"Cargados {len(data)} valores 'last' para peticiones settled")
                return data
        return {}
    except Exception as e:
        logger.error(f"Error cargando valores 'last': {e}")
        return {}

def save_settled_last_values(last_values: Dict[str, int]) -> None:
    """
    Guarda los valores 'last' para cada sport_id en el archivo JSON.
    
    Args:
        last_values (Dict[str, int]): Diccionario con los valores 'last' por sport_id.
    """
    try:
        with open(SETTLED_LAST_FILE, 'w') as f:
            json.dump(last_values, f)
        logger.info(f"Guardados {len(last_values)} valores 'last' para peticiones settled")
    except Exception as e:
        logger.error(f"Error guardando valores 'last': {e}")

def load_sports_mapping() -> Dict[str, int]:
    """
    Carga el mapeo de deportes desde el archivo JSON.
    
    Returns:
        Dict[str, int]: Diccionario con el mapeo de nombres de deportes a sus IDs.
    """
    try:
        if not os.path.exists(SPORTS_JSON_FILE):
            logger.warning(f"Archivo de deportes no encontrado: {SPORTS_JSON_FILE}")
            return DEFAULT_SPORTS_MAPPING
        
        with open(SPORTS_JSON_FILE, 'r') as f:
            sports_data = json.load(f)
        
        sports_mapping = {}
        for sport in sports_data.get('sports', []):
            if isinstance(sport, dict) and 'name' in sport and 'id' in sport:
                sports_mapping[sport.get('name')] = sport.get('id')
                # También guardar versiones en minúsculas para búsquedas insensibles a mayúsculas
                sports_mapping[sport.get('name').lower()] = sport.get('id')
        
        if not sports_mapping:
            logger.warning("No se encontraron deportes en el archivo")
            return DEFAULT_SPORTS_MAPPING
            
        logger.info(f"Deportes cargados: {len(sports_mapping)//2} deportes disponibles")
        return sports_mapping
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar el archivo de deportes: {e}")
        return DEFAULT_SPORTS_MAPPING
    except Exception as e:
        logger.error(f"Error cargando el archivo de deportes: {e}")
        return DEFAULT_SPORTS_MAPPING

# ===================== FUNCIONES DE COMUNICACIÓN =====================
def send_telegram_message(json_data: Dict[str, Any]) -> bool:
    """
    Envía un mensaje JSON a un grupo de Telegram en formato de código.
    
    Args:
        json_data (Dict[str, Any]): Datos a enviar en formato JSON.
    
    Returns:
        bool: True si el mensaje se envió correctamente, False en caso contrario.
    """
    try:
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        formatted_json = json.dumps(json_data, indent=4, default=str)
        
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"📊 *Match update:*\n```json\n{formatted_json}\n```",
            "parse_mode": "Markdown"
        }
        
        response = requests.post(telegram_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Mensaje enviado a Telegram: {json_data.get('game_id', 'N/A')}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a Telegram: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al enviar mensaje a Telegram: {str(e)}")
        return False

def send_error_notification(message: str) -> bool:
    """
    Envía una notificación de error por Telegram.
    
    Args:
        message (str): Mensaje de error a enviar.
    
    Returns:
        bool: True si el mensaje se envió correctamente, False en caso contrario.
    """
    try:
        return send_telegram_message({"critical": message})
    except Exception as e:
        logger.error(f"No se pudo enviar notificación por Telegram: {e}")
        return False
    
# ===================== FUNCIONES DE PROCESAMIENTO DE DATOS =====================
def read_bets_from_json() -> List[Dict[str, Any]]:
    """
    Lee las apuestas del archivo JSON de manera segura.
    
    Returns:
        List[Dict[str, Any]]: Lista de apuestas leídas del archivo.
    """
    try:
        if not os.path.exists(JSON_INPUT_FILE):
            logger.info(f"El archivo {JSON_INPUT_FILE} no existe.")
            return []
            
        with open(JSON_INPUT_FILE, 'r', encoding='utf-8') as file:
            file_content = file.read()
            
        if not file_content.strip():
            logger.info(f"El archivo {JSON_INPUT_FILE} está vacío.")
            return []
            
        data = json.loads(file_content)
        
        if not isinstance(data, list):
            logger.warning(f"El contenido de {JSON_INPUT_FILE} no es una lista. Tipo: {type(data)}")
            if isinstance(data, dict):
                # Convertir a lista si es un diccionario
                return [data]
            return []
            
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar el archivo JSON {JSON_INPUT_FILE}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error al leer el archivo {JSON_INPUT_FILE}: {e}")
        return []
    
def get_normalized_team(team_name: str, league: str = "NBA") -> str:
    """
    Obtiene el nombre normalizado del equipo usando el diccionario correspondiente.
    
    Args:
        team_name (str): Nombre del equipo a normalizar.
        league (str): Liga del equipo.
        
    Returns:
        str: Nombre normalizado del equipo.
    """
    if not team_name:
        return ""
    
    team_name = team_name.lower().strip()
    
    # Usar el diccionario correspondiente según la liga
    if teams_imported:
        if league.upper() == "NBA" and hasattr(sys.modules['teams'], 'nba_teams'):
            normalized = nba_teams.get(team_name)
            if normalized:
                logger.debug(f"Nombre normalizado de '{team_name}' en NBA: '{normalized}'")
                return normalized
                
        # Agregar soporte para otros diccionarios si existen
        if league.upper() == "NCAAB" and hasattr(sys.modules['teams'], 'ncaab_teams'):
            ncaab_teams = getattr(sys.modules['teams'], 'ncaab_teams', {})
            normalized = ncaab_teams.get(team_name)
            if normalized:
                logger.debug(f"Nombre normalizado de '{team_name}' en NCAAB: '{normalized}'")
                return normalized
                
        # Intentar en un diccionario general si existe
        if hasattr(sys.modules['teams'], 'all_teams'):
            all_teams = getattr(sys.modules['teams'], 'all_teams', {})
            normalized = all_teams.get(team_name)
            if normalized:
                logger.debug(f"Nombre normalizado de '{team_name}' en diccionario general: '{normalized}'")
                return normalized
    
    # Si no encuentra en el diccionario o no hay diccionario, devolver el original
    return team_name

def normalize_and_verify_teams(bet_info: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Normaliza y verifica los nombres de equipos en bet_info usando teams.py
    antes de hacer peticiones a la API.
    
    Args:
        bet_info (Dict[str, Any]): Información de la apuesta.
        
    Returns:
        Tuple[Dict[str, Any], List[str]]: Versión actualizada de bet_info con nombres 
        normalizados y lista de nombres de equipos para búsqueda.
    """
    visitor = bet_info.get('visitor', '')
    home = bet_info.get('home', '')
    league = bet_info.get('league', 'NBA')
    
    # Lista para almacenar todos los posibles nombres de equipos para búsqueda
    search_names = []
    
    # Normalizar usando el diccionario de equipos
    normalized_visitor = get_normalized_team(visitor, league)
    normalized_home = get_normalized_team(home, league)
    
    # Actualizar bet_info con nombres normalizados si cambiaron
    if normalized_visitor != visitor:
        bet_info['original_visitor'] = visitor  # Guardar original
        bet_info['visitor'] = normalized_visitor
        logger.info(f"Nombre de equipo visitante normalizado: '{visitor}' -> '{normalized_visitor}'")
    
    if normalized_home != home:
        bet_info['original_home'] = home  # Guardar original
        bet_info['home'] = normalized_home
        logger.info(f"Nombre de equipo local normalizado: '{home}' -> '{normalized_home}'")
    
    # Agregar nombres normalizados a la lista de búsqueda
    if normalized_visitor:
        search_names.append(normalized_visitor)
    if normalized_home:
        search_names.append(normalized_home)
    
    # También agregar los nombres originales si son diferentes a los normalizados
    if visitor and visitor != normalized_visitor and visitor not in search_names:
        search_names.append(visitor)
    if home and home != normalized_home and home not in search_names:
        search_names.append(home)
    
    # Extraer del campo the_bet si está disponible
    the_bet = (bet_info.get('the_bet', '') or '').lower().strip()
    if the_bet and not (visitor or home):
        # Intentar extraer nombres de equipos del campo the_bet
        possible_team = re.search(r'^([a-z]+\s*[a-z]*)', the_bet)
        if possible_team:
            extracted_team = possible_team.group(1).strip()
            normalized_extracted = get_normalized_team(extracted_team, league)
            
            if normalized_extracted and normalized_extracted not in search_names:
                search_names.append(normalized_extracted)
                logger.info(f"Equipo extraído y normalizado de the_bet: '{extracted_team}' -> '{normalized_extracted}'")
            elif extracted_team and extracted_team not in search_names:
                search_names.append(extracted_team)
                logger.info(f"Equipo extraído de the_bet: '{extracted_team}'")
    
    # Para apuestas de la NCAA, intentar extraer más variantes de nombres
    if league.upper() in NCAA_LEAGUES:
        for team_name in list(search_names):  # Usar una copia para poder modificar la original
            # Para "north carolina", también buscar "unc" si está en el diccionario
            normalized_abbr = get_normalized_team(f"abbr_{team_name}", league)
            if normalized_abbr != f"abbr_{team_name}" and normalized_abbr not in search_names:
                search_names.append(normalized_abbr)
                logger.info(f"Añadida abreviatura para '{team_name}': '{normalized_abbr}'")
                
            # Para nombres compuestos como "north carolina", también buscar versiones parciales
            if " " in team_name:
                words = team_name.split()
                if len(words) > 1:
                    # Intentar con la primera palabra (ej: "north" de "north carolina")
                    if words[0] not in search_names:
                        search_names.append(words[0])
                    # Intentar con combinaciones (para nombres de 3+ palabras)
                    if len(words) > 2:
                        two_word = f"{words[0]} {words[1]}"
                        if two_word not in search_names:
                            search_names.append(two_word)
    
    logger.info(f"Nombres de equipos para búsqueda: {search_names}")
    return bet_info, search_names

def map_bet_info(bet_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Mapea los datos del registro de apuesta a la estructura esperada.
    
    Args:
        bet_record (Dict[str, Any]): Registro de apuesta a mapear.
        
    Returns:
        Optional[Dict[str, Any]]: Información de la apuesta mapeada o None si no se pudo mapear.
    """
    try:
        if not isinstance(bet_record, dict):
            logger.warning(f"Registro de apuesta no es un diccionario: {type(bet_record)}")
            return None
        
        # Obtener información del deporte y la liga
        sport = bet_record.get('sport', 'Basketball').strip()
        league = bet_record.get('league', 'NBA').strip()
        
        # Normalizar la liga si corresponde
        normalized_league = LEAGUE_MAPPING.get(league.upper(), league)
        
        # Obtener nombres de equipos (visitante y local)
        visitor_team = bet_record.get('visitor', '').strip().lower() if bet_record.get('visitor') else ''
        home_team = bet_record.get('home', '').strip().lower() if bet_record.get('home') else ''
        the_bet = bet_record.get('the_bet', '').strip().lower()
        
        # Si visitor o home están vacíos, intentar extraer del campo the_bet
        if not visitor_team and not home_team and the_bet:
            # Extraer la primera parte antes de cualquier número o símbolo +/-
            match = re.search(r'^([a-z]+)', the_bet)
            if match:
                visitor_team = match.group(1).strip()
        
        # Normalizar usando el diccionario de equipos
        normalized_visitor = get_normalized_team(visitor_team, league)
        normalized_home = get_normalized_team(home_team, league)
        
        # Si aún no tenemos información de equipo, no podemos procesar
        if not normalized_visitor and not normalized_home:
            logger.warning(f"No se pudo determinar información de equipos para: {bet_record}")
            return None
        
        # Crear el objeto de información de la apuesta
        bet_info = {
            'id': bet_record.get('id'),
            'period': bet_record.get('period', ''),  # Guardar el periodo
            'visitor': normalized_visitor,
            'home': normalized_home,
            'original_visitor': visitor_team,
            'original_home': home_team,
            'sport': sport,
            'league': normalized_league,  # Usar la liga normalizada
            'original_league': league,    # Guardar la liga original
            'bet_type': bet_record.get('bet_type'),
            'the_bet': bet_record.get('the_bet'),
            'line': bet_record.get('line')
        }
        
        return bet_info
    except Exception as e:
        logger.error(f"Error al mapear bet_info: {e}")
        return None

def get_league_id(sport: str, league: str) -> Optional[int]:
    """
    Dado un nombre de deporte y una liga, obtiene el ID de la liga desde el archivo JSON correspondiente.
    
    Args:
        sport (str): Nombre del deporte.
        league (str): Nombre de la liga.
        
    Returns:
        Optional[int]: ID de la liga o None si no se encuentra.
    """
    try:
        sport_file = f"{sport.lower()}.json"
        if not os.path.exists(sport_file):
            logger.warning(f"No se encontró el archivo para el deporte: {sport_file}")
            return None

        with open(sport_file, "r", encoding="utf-8") as f:
            leagues = json.load(f)

        for entry in leagues:
            if entry.get("name", "").strip().lower() == league.strip().lower():
                return entry.get("id")
        logger.warning(f"No se encontró el ID de la liga '{league}' en {sport_file}")
    except Exception as e:
        logger.error(f"Error al obtener leagueId: {e}")
    
    return None

def format_result(event_result: Dict[str, Any], home_team: str, away_team: str, 
                 rotation_number: Optional[int] = None) -> Dict[str, Any]:
    """
    Formatea los datos del partido de manera segura.
    
    Args:
        event_result (Dict[str, Any]): Resultado del evento desde la API.
        home_team (str): Nombre del equipo local.
        away_team (str): Nombre del equipo visitante.
        rotation_number (Optional[int]): Número de rotación del partido.
        
    Returns:
        Dict[str, Any]: Datos formateados del partido.
    """
    try:
        game_id = event_result.get('id')
        periods = event_result.get('periods', [])

        result = {
            "game_id": game_id,
            "rotation_number": rotation_number,
            "teams": {
                "home": {"name": home_team, "score": None},
                "away": {"name": away_team, "score": None}
            },
            "periods": []
        }

        final_score = None
        for p in periods:
            if p.get('number') == 0:
                final_score = p
                break

        for period in periods:
            period_data = {
                "number": period.get('number'),
                "settled_at": period.get('settledAt')
            }
            
            # Añadir los scores de manera segura
            if home_team:
                period_data[home_team] = period.get('team2Score')
            if away_team:
                period_data[away_team] = period.get('team1Score')
                
            result["periods"].append(period_data)

        # Si encontramos el período final, asignamos el score final
        if final_score:
            if "away" in result["teams"] and result["teams"]["away"] is not None:
                result["teams"]["away"]["score"] = final_score.get('team1Score')
            if "home" in result["teams"] and result["teams"]["home"] is not None:
                result["teams"]["home"]["score"] = final_score.get('team2Score')
        
        return result
    except Exception as e:
        logger.error(f"Error en format_result: {str(e)}")
        return {"error": f"Error formateando resultado: {str(e)}"}

# ===================== FUNCIONES PRINCIPALES DE API =====================
def build_api_url(path: str, params: Dict[str, Any]) -> str:
    """
    Construye una URL para la API con los parámetros dados.
    
    Args:
        path (str): Ruta de la API.
        params (Dict[str, Any]): Parámetros para la URL.
        
    Returns:
        str: URL completa para la API.
    """
    param_strings = []
    for key, value in params.items():
        if value is not None:
            param_strings.append(f"{key}={value}")
    
    query_string = "&".join(param_strings)
    return f"{path}?{query_string}"

def search_in_settled(sport_id: int, league_ids: Optional[str] = None, 
                     game_id: Optional[str] = None, rotation_number: Optional[int] = None, 
                     home_team: Optional[str] = None, away_team: Optional[str] = None) -> Dict[str, Any]:
    """
    Busca el partido en settled usando el ID del evento, incluyendo el parámetro since.
    
    Args:
        sport_id (int): ID del deporte.
        league_ids (Optional[str]): IDs de ligas, separados por comas.
        game_id (Optional[str]): ID del juego a buscar.
        rotation_number (Optional[int]): Número de rotación del partido.
        home_team (Optional[str]): Nombre del equipo local.
        away_team (Optional[str]): Nombre del equipo visitante.
        
    Returns:
        Dict[str, Any]: Resultado de la búsqueda.
    """
    global settled_last_values
    
    try:
        # Obtener el valor 'since' para este sport_id
        sport_id_key = str(sport_id)
        since_value = settled_last_values.get(sport_id_key, 0)
        
        # Convertir since a base64 si es necesario (no es 0)
        since_param = "0" if since_value == 0 else str(base64.b64encode(str(since_value).encode()), 'utf-8')
        
        # Preparar los parámetros de la URL
        params = {
            "sportId": sport_id,
            "leagueIds": league_ids or "493",  # 493 por defecto si no se proporciona
            "since": since_param
        }
        
        # Construir la URL usando el path de settled
        settled_url = build_api_url(SETTLED_API_PATH, params)
        
        logger.info(f"Buscando partido en settled (sportId={sport_id}, since={since_param})")
        if game_id:
            logger.info(f"Buscando partido específico con ID {game_id}")
        
        auth = HTTPBasicAuth(username, password)
        settled_response = requests.get(settled_url, auth=auth, timeout=30)
        settled_response.raise_for_status()
        settled_data = settled_response.json()
        
        # Actualizar el valor 'last' si está presente en la respuesta
        if 'last' in settled_data:
            last_value = settled_data.get('last')
            settled_last_values[sport_id_key] = last_value
            logger.info(f"Valor 'last' actualizado para sport_id {sport_id}: {last_value}")
            save_settled_last_values(settled_last_values)

        # Si no estamos buscando un juego específico, devolver los datos completos
        if not game_id:
            return settled_data
            
        # Buscar el juego específico en los datos
        for league_result in settled_data.get('leagues', []):
            for event_result in league_result.get('events', []):
                if event_result.get('id') == game_id:
                    logger.info(f"¡ÉXITO! Partido encontrado en settled, ID={game_id}")
                    
                    # Verificar si tiene períodos antes de formatearlo
                    if not event_result.get('periods'):
                        logger.warning(f"Partido con ID {game_id} encontrado en settled pero no tiene períodos todavía")
                        return {"error": f"Match with ID '{game_id}' found in settled but has no periods yet."}
                    
                    # Si no tenemos los nombres de los equipos, intentar extraerlos del resultado
                    if not home_team or not away_team:
                        logger.info(f"No se tienen nombres de equipos para ID {game_id}, intentando extraer del resultado")
                        try:
                            # Intentar obtener nombres de equipos del resultado
                            home_team = event_result.get('homeName')
                            away_team = event_result.get('awayName')
                            logger.info(f"Nombres extraídos: Home={home_team}, Away={away_team}")
                        except Exception as e:
                            logger.warning(f"No se pudieron extraer nombres de equipos: {e}")
                    
                    return format_result(event_result, home_team, away_team, rotation_number)

        logger.info(f"Partido con ID '{game_id}' aún no está en settled.")
        return {"error": f"Match with ID '{game_id}' not found in settled yet."}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión en settled: {str(e)}")
        return {"error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error(f"Error inesperado en search_in_settled: {str(e)}")
        return {"error": f"Error inesperado: {str(e)}"}

def get_sport_id_from_bet(bet_info: Dict[str, Any]) -> int:
    """
    Obtiene el ID del deporte a partir de la información de la apuesta.
    
    Args:
        bet_info (Dict[str, Any]): Información de la apuesta.
        
    Returns:
        int: ID del deporte.
    """
    sport = bet_info.get('sport')
    league = bet_info.get('league')
    
    # Obtener el ID del deporte del sport o la league
    sport_id = SPORTS_MAPPING.get(sport) or SPORTS_MAPPING.get(sport.lower())
    
    # Si no encuentra, intentar con league
    if not sport_id:
        sport_id = SPORTS_MAPPING.get(league) or SPORTS_MAPPING.get(league.lower())
        
    # Fallback a Basketball
    if not sport_id:
        sport_id = 4  # Basketball por defecto
        logger.warning(f"No se encontró ID para '{sport}' o '{league}', usando Basketball (4)")
    
    return sport_id

def get_game_data(bet_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene los datos del partido basado en la información de equipos sin importar si son home o away.
    
    Args:
        bet_info (Dict[str, Any]): Información de la apuesta.
        
    Returns:
        Dict[str, Any]: Datos del partido o mensaje de error.
    """
    try:
        # Normalizar y verificar equipos antes de hacer peticiones
        bet_info, team_names = normalize_and_verify_teams(bet_info)
        
        # Extraer información básica
        sport = bet_info.get('sport')
        league = bet_info.get('league')
        
        logger.info(f"Buscando partido para los equipos: {team_names}, Sport={sport}, League={league}")
        
        # Verificar que tengamos al menos un equipo
        if not team_names:
            logger.warning("No hay información de equipos para buscar el partido")
            return {"error": "No team information available to search for the match"}
        
        # Obtener el ID del deporte
        sport_id = get_sport_id_from_bet(bet_info)
        
        # Obtener ID de liga si está disponible
        league_id = get_league_id(sport, league)
        league_ids_param = f"{league_id}" if league_id else "493"
        
        auth = HTTPBasicAuth(username, password)
        
        return fetch_game_data(bet_info, team_names, league_ids_param, sport_id, auth, league)
    except Exception as e:
        logger.error(f"Error en get_game_data: {str(e)}")
        return {"error": f"Error al obtener datos del juego: {str(e)}"}

def fetch_game_data(bet_info: Dict[str, Any], team_names: List[str], 
                   league_ids: str, sport_id: int, 
                   auth: HTTPBasicAuth, league: str) -> Dict[str, Any]:
    """
    Función principal que implementa la estrategia de búsqueda de datos de partidos.
    
    Args:
        bet_info (Dict[str, Any]): Información de la apuesta.
        team_names (List[str]): Lista de nombres de equipos para búsqueda.
        league_ids (str): IDs de ligas separados por comas.
        sport_id (int): ID del deporte.
        auth (HTTPBasicAuth): Autenticación para la API.
        league (str): Nombre de la liga.
        
    Returns:
        Dict[str, Any]: Datos del partido o mensaje de error.
    """
    # PASO 1: BUSCAR EN IDS GUARDADOS
    logger.info("PASO 1: Revisando IDs guardados de partidos para estos equipos")
    possible_game_ids = []
    
    # Buscar por ID de apuesta
    if bet_info.get('id'):
        bet_id = bet_info.get('id')
        logger.info(f"Usando bet_id de la apuesta: {bet_id}")
        
        for key, value in last_game_ids.items():
            if str(bet_id) == str(key) or str(bet_id) in str(key):
                logger.info(f"Encontrado game_id para bet_id {bet_id}: {value}")
                possible_game_ids.append(value)
    
    # Buscar por combinaciones de equipos
    for team1 in team_names:
        for team2 in team_names:
            if team1 == team2:
                continue
                
            team_key = f"{team1}_{team2}".lower().replace(' ', '')
            
            if team_key in last_game_ids:
                saved_game_id = last_game_ids[team_key]
                logger.info(f"Encontrado ID guardado para equipos {team1} vs {team2}: {saved_game_id}")
                possible_game_ids.append(saved_game_id)
    
    # Eliminar duplicados de IDs
    unique_game_ids = list(set(possible_game_ids))
    logger.info(f"IDs únicos encontrados en caché: {unique_game_ids}")
    
    # Buscar en settled usando IDs guardados
    for game_id in unique_game_ids:
        logger.info(f"Verificando directamente en settled el partido con ID: {game_id}")
        result = search_in_settled(sport_id, league_ids, game_id)
        
        if not result.get("error"):
            logger.info(f"¡ÉXITO! Partido encontrado en settled usando ID guardado: {game_id}")
            return result
        elif "not found in settled yet" in result.get("error", ""):
            logger.info(f"Partido con ID {game_id} aún no está en settled, continuando búsqueda...")
        else:
            logger.warning(f"Error al buscar partido con ID {game_id}: {result.get('error')}")
    
    # PASO 2: BUSCAR EN FIXTURES
    return search_in_fixtures(bet_info, team_names, unique_game_ids, league_ids, sport_id, auth, league)

def search_in_fixtures(bet_info: Dict[str, Any], team_names: List[str], 
                      unique_game_ids: List[str], league_ids: str, 
                      sport_id: int, auth: HTTPBasicAuth, league: str) -> Dict[str, Any]:
    """
    Busca el partido en la API de fixtures y maneja diferentes escenarios.
    
    Args:
        bet_info (Dict[str, Any]): Información de la apuesta.
        team_names (List[str]): Lista de nombres de equipos para búsqueda.
        unique_game_ids (List[str]): Lista de IDs únicos de juego.
        league_ids (str): IDs de ligas separados por comas.
        sport_id (int): ID del deporte.
        auth (HTTPBasicAuth): Autenticación para la API.
        league (str): Nombre de la liga.
        
    Returns:
        Dict[str, Any]: Datos del partido o mensaje de error.
    """
    logger.info("PASO 2: Buscando partidos en fixtures")
    
    game_id = None
    home_team_full = None
    away_team_full = None
    rotation_number = None
    fixtures_data = None
    fixtures_429_error = False
    
    try:
        # Construir parámetros para la URL de fixtures
        params = {
            "sportId": sport_id,
            "leagueIds": league_ids,
            "since": "0"
        }
        fixtures_url = build_api_url(SETTLED_API_PATH, params)
        
        # Primero buscar usando IDs guardados
        if unique_game_ids:
            fixtures_data = fetch_fixtures_data(fixtures_url, auth)
            
            if fixtures_data:
                game_match = find_game_by_ids(fixtures_data, unique_game_ids)
                if game_match:
                    game_id, home_team_full, away_team_full, rotation_number = game_match
        
        # Si no encontramos por ID, buscar por nombres de equipos
        if not game_id:
            if not fixtures_data:
                fixtures_data = fetch_fixtures_data(fixtures_url, auth)
                
            if fixtures_data:
                game_match = find_game_by_team_names(fixtures_data, team_names, league, bet_info)
                if game_match:
                    game_id, home_team_full, away_team_full, rotation_number = game_match
    
    except requests.exceptions.HTTPError as e:
        if "429" in str(e):
            logger.error(f"Error 429 (Too Many Requests) al acceder a fixtures: {str(e)}")
            fixtures_429_error = True
            
            if unique_game_ids:
                game_id = unique_game_ids[0]
                logger.info(f"Usando ID guardado {game_id} debido a error 429 en fixtures")
        else:
            logger.error(f"Error HTTP en fixtures: {str(e)}")
            return {"error": f"Error HTTP: {str(e)}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión en fixtures: {str(e)}")
        
        if unique_game_ids:
            game_id = unique_game_ids[0]
            logger.info(f"Usando ID guardado {game_id} debido a error de conexión en fixtures")
        else:
            return {"error": f"Error de conexión: {str(e)}"}
    
    # PASO 3: USAR ID GUARDADO SI NO ENCONTRAMOS EN FIXTURES O HUBO ERROR
    if (not game_id and unique_game_ids) or fixtures_429_error:
        if not game_id and unique_game_ids:
            game_id = unique_game_ids[0]
        
        msg = "Error 429 detectado" if fixtures_429_error else "No se encontró partido en fixtures"
        logger.info(f"{msg}, usando ID guardado: {game_id} para buscar en settled")
        
        return search_in_settled(sport_id, league_ids, game_id)
    
    # Si no encontramos el partido en ninguna parte
    if not game_id:
        # Para NCAA, mostrar equipos disponibles para diagnóstico
        log_available_ncaa_teams(fixtures_data, league)
        
        team_names_str = ", ".join(team_names)
        logger.info(f"No se encontró partido para {team_names_str} en fixtures ni IDs guardados.")
        return {"error": f"No match found for teams {team_names_str} in fixtures."}
    
    # PASO 4: SI ENCONTRAMOS EL PARTIDO EN FIXTURES, BUSCAR EN SETTLED
    return search_in_settled(sport_id, league_ids, game_id, rotation_number, home_team_full, away_team_full)

def fetch_fixtures_data(fixtures_url: str, auth: HTTPBasicAuth) -> Optional[Dict[str, Any]]:
    """
    Obtiene los datos de fixtures de la API.
    
    Args:
        fixtures_url (str): URL de la API de fixtures.
        auth (HTTPBasicAuth): Autenticación para la API.
        
    Returns:
        Optional[Dict[str, Any]]: Datos obtenidos o None si hay error.
    """
    try:
        fixtures_response = requests.get(fixtures_url, auth=auth, timeout=30)
        fixtures_response.raise_for_status()
        return fixtures_response.json()
    except Exception as e:
        logger.error(f"Error al obtener datos de fixtures: {e}")
        return None

def find_game_by_ids(fixtures_data: Dict[str, Any], game_ids: List[str]) -> Optional[Tuple[str, str, str, str]]:
    """
    Busca un partido por IDs en los datos de fixtures.
    
    Args:
        fixtures_data (Dict[str, Any]): Datos de fixtures de la API.
        game_ids (List[str]): Lista de IDs de juego a buscar.
        
    Returns:
        Optional[Tuple[str, str, str, str]]: Tupla con game_id, home_team, away_team, rotation_number o None si no encuentra.
    """
    for league_info in fixtures_data.get('league', []):
        for event in league_info.get('events', []):
            if event.get('id') in game_ids:
                game_id = event.get('id')
                home_team_full = event.get('home')
                away_team_full = event.get('away')
                rotation_number = event.get('rotNum')
                logger.info(f"Partido encontrado en fixtures usando ID guardado: {game_id}, {away_team_full} @ {home_team_full}")
                return game_id, home_team_full, away_team_full, rotation_number
    return None

def find_game_by_team_names(fixtures_data: Dict[str, Any], team_names: List[str], 
                           league: str, bet_info: Dict[str, Any]) -> Optional[Tuple[str, str, str, str]]:
    """
    Busca un partido por nombres de equipos en los datos de fixtures.
    
    Args:
        fixtures_data (Dict[str, Any]): Datos de fixtures de la API.
        team_names (List[str]): Lista de nombres de equipos para búsqueda.
        league (str): Nombre de la liga.
        bet_info (Dict[str, Any]): Información de la apuesta.
        
    Returns:
        Optional[Tuple[str, str, str, str]]: Tupla con game_id, home_team, away_team, rotation_number o None si no encuentra.
    """
    global last_game_ids
    
    for league_info in fixtures_data.get('league', []):
        # Verificar si la liga coincide
        if not is_matching_league(league_info, league):
            logger.debug(f"Saltando liga {league_info.get('name')}, buscando {league}")
            continue
            
        for event in league_info.get('events', []):
            logger.info(f"Analizando partido en liga: {league_info.get('name')} (ID: {league_info.get('id')})")
            
            # Obtener nombres de equipos
            api_home = event.get('home', '').lower()
            api_away = event.get('away', '').lower()
            
            # Verificar coincidencia de equipos
            if is_team_match(api_home, api_away, team_names, league):
                game_id = event.get('id')
                home_team_full = event.get('home')
                away_team_full = event.get('away')
                rotation_number = event.get('rotNum')
                
                # Guardar ID para futuras referencias
                save_game_id_mappings(game_id, api_home, api_away, team_names, bet_info)
                
                logger.info(f"Partido encontrado: {away_team_full} @ {home_team_full}, ID={game_id}, RotNum={rotation_number}")
                return game_id, home_team_full, away_team_full, rotation_number
    
    return None

def is_matching_league(league_info: Dict[str, Any], search_league: str) -> bool:
    """
    Determina si una liga de la API coincide con la liga buscada.
    
    Args:
        league_info (Dict[str, Any]): Información de la liga desde la API.
        search_league (str): Liga que estamos buscando.
        
    Returns:
        bool: True si la liga coincide, False en caso contrario.
    """
    api_league_name = league_info.get('name', '').upper()
    ncaa_case = search_league.upper() in NCAA_LEAGUES
    
    if ncaa_case:
        # Para NCAA masculino, rechazar ligas femeninas
        if "WNCAA" in api_league_name or "WOMEN" in api_league_name:
            return False
            
        # Aceptar ligas NCAA o College Basketball
        if "NCAA" in api_league_name:
            return True
        if "COLLEGE" in api_league_name and "BASKETBALL" in api_league_name:
            return True
        return False
    else:
        # Para ligas regulares, coincidencia exacta
        return search_league.upper() == api_league_name or search_league == league_info.get('name')

def is_team_match(api_home: str, api_away: str, team_names: List[str], league: str) -> bool:
    """
    Determina si alguno de los equipos de búsqueda coincide con los equipos de la API.
    
    Args:
        api_home (str): Nombre del equipo local según la API.
        api_away (str): Nombre del equipo visitante según la API.
        team_names (List[str]): Lista de nombres de equipos para búsqueda.
        league (str): Nombre de la liga.
        
    Returns:
        bool: True si hay coincidencia, False en caso contrario.
    """
    # 1. Verificación exacta
    for team_name in team_names:
        if team_name == api_home or team_name == api_away:
            logger.info(f"✅ Coincidencia EXACTA: '{team_name}' con home='{api_home}' o away='{api_away}'")
            return True
    
    # 2. Verificación flexible
    for team_name in team_names:
        is_ncaa = league.upper() in NCAA_LEAGUES
        
        if is_ncaa:
            # Verificación flexible para NCAA
            if match_ncaa_team(team_name, api_home, api_away):
                return True
        else:
            # Verificación regular para otras ligas
            if (team_name in api_away or api_away in team_name or 
                team_name in api_home or api_home in team_name):
                logger.info(f"Coincidencia de equipo: {team_name} coincide con home={api_home} o away={api_away}")
                return True
    
    return False

def match_ncaa_team(team_name: str, api_home: str, api_away: str) -> bool:
    """
    Realiza verificaciones específicas para equipos NCAA.
    
    Args:
        team_name (str): Nombre del equipo a verificar.
        api_home (str): Nombre del equipo local según la API.
        api_away (str): Nombre del equipo visitante según la API.
        
    Returns:
        bool: True si hay coincidencia, False en caso contrario.
    """
    api_away_words = api_away.split()
    api_home_words = api_home.split()
    team_name_words = team_name.split()
    
    # Verificar coincidencia al inicio
    if (api_away.startswith(team_name) or api_home.startswith(team_name)):
        logger.info(f"Coincidencia NCAA (inicio): {team_name} coincide con home={api_home} o away={api_away}")
        return True
        
    # Verificar coincidencia como palabra individual
    if (team_name in api_away_words or team_name in api_home_words):
        logger.info(f"Coincidencia NCAA (palabra): {team_name} coincide con home={api_home} o away={api_away}")
        return True
        
    # Para nombres compuestos
    if len(team_name_words) > 1:
        # Verificar en away
        if len(api_away_words) >= len(team_name_words):
            if all(team_name_words[i] == api_away_words[i] for i in range(len(team_name_words))):
                logger.info(f"Coincidencia NCAA (palabras múltiples en away): {team_name} coincide con {api_away}")
                return True
                
        # Verificar en home
        if len(api_home_words) >= len(team_name_words):
            if all(team_name_words[i] == api_home_words[i] for i in range(len(team_name_words))):
                logger.info(f"Coincidencia NCAA (palabras múltiples en home): {team_name} coincide con {api_home}")
                return True
    
    return False

def save_game_id_mappings(game_id: str, api_home: str, api_away: str, 
                         team_names: List[str], bet_info: Dict[str, Any]) -> None:
    """
    Guarda el ID del juego con varias combinaciones de nombres de equipos.
    
    Args:
        game_id (str): ID del juego.
        api_home (str): Nombre del equipo local según la API.
        api_away (str): Nombre del equipo visitante según la API.
        team_names (List[str]): Lista de nombres de equipos.
        bet_info (Dict[str, Any]): Información de la apuesta.
    """
    global last_game_ids
    
    # Guardar combinaciones de los nombres de la API
    api_home_lower = api_home.replace(' ', '')
    api_away_lower = api_away.replace(' ', '')
    
    team_key1 = f"{api_away_lower}_{api_home_lower}".lower()
    team_key2 = f"{api_home_lower}_{api_away_lower}".lower()
    last_game_ids[team_key1] = game_id
    last_game_ids[team_key2] = game_id
    
    # Guardar con el ID de la apuesta si está disponible
    if bet_info.get('id'):
        bet_id_key = f"bet_{bet_info.get('id')}"
        last_game_ids[bet_id_key] = game_id
        logger.info(f"Guardando ID {game_id} para bet_id {bet_info.get('id')}")
    
    # Guardar combinaciones con los nombres normalizados
    for team1 in team_names:
        for team2 in team_names:
            if team1 != team2:
                team_key = f"{team1}_{team2}".lower().replace(' ', '')
                last_game_ids[team_key] = game_id
    
    # Guardar los IDs en el archivo para persistencia
    save_game_ids(last_game_ids)

def log_available_ncaa_teams(fixtures_data: Optional[Dict[str, Any]], league: str) -> None:
    """
    Registra equipos NCAA disponibles para ayudar al diagnóstico.
    
    Args:
        fixtures_data (Optional[Dict[str, Any]]): Datos de fixtures de la API.
        league (str): Nombre de la liga.
    """
    if not fixtures_data or league.upper() not in NCAA_LEAGUES:
        return
        
    logger.info("Realizando búsqueda exhaustiva para equipo NCAA...")
    available_teams = []
    
    for league_info in fixtures_data.get('league', []):
        api_league_name = league_info.get('name', '').upper()
        if "NCAA" in api_league_name:
            for event in league_info.get('events', []):
                available_teams.append(f"HOME: {event.get('home')}")
                available_teams.append(f"AWAY: {event.get('away')}")
    
    # Limitar para no saturar el log
    if available_teams:
        logger.info(f"Equipos NCAA disponibles (muestra): {available_teams[:20]}")
        if len(available_teams) > 20:
            logger.info(f"...y {len(available_teams) - 20} más")

def handle_request_exception(team_names: List[str], exception: Exception, 
                           settled_url: str, auth: HTTPBasicAuth) -> Dict[str, Any]:
    """
    Maneja excepciones de solicitud HTTP usando estrategias de recuperación.
    
    Args:
        team_names (List[str]): Lista de nombres de equipos.
        exception (Exception): Excepción capturada.
        settled_url (str): URL de la API de settled.
        auth (HTTPBasicAuth): Autenticación para la API.
        
    Returns:
        Dict[str, Any]: Resultado de la recuperación o mensaje de error.
    """
    global last_game_ids
    
    # Intentar usar IDs guardados
    possible_game_ids = []
    
    for team1 in team_names:
        for team2 in team_names:
            if team1 == team2:
                continue
                
            team_key = f"{team1}_{team2}".lower().replace(' ', '')
            
            if team_key in last_game_ids:
                saved_game_id = last_game_ids[team_key]
                possible_game_ids.append(saved_game_id)
    
    # Eliminar duplicados
    unique_game_ids = list(set(possible_game_ids))
    
    if unique_game_ids:
        game_id = unique_game_ids[0]
        logger.info(f"Usando ID guardado {game_id} debido a error de conexión general")
        return search_in_settled(settled_url, auth, game_id, None)
        
    return {"error": f"Error de conexión: {str(exception)}"}

# ===================== PROCESAMIENTO DE APUESTAS =====================
def process_bet_info(bet_info: Dict[str, Any]) -> None:
    """
    Procesa una apuesta y envía los resultados de manera segura.
    
    Args:
        bet_info (Dict[str, Any]): Información de la apuesta.
    """
    if not bet_info or not isinstance(bet_info, dict):
        return
    
    try:
        # Verificar si tiene los campos necesarios
        if (not bet_info.get('visitor') and not bet_info.get('home')) or not bet_info.get('sport'):
            error_msg = {"error": f"JSON inválido para la apuesta ID {bet_info.get('id', 'N/A')}. Debe contener información de al menos un equipo y deporte."}
            logger.warning(error_msg['error'])
            send_telegram_message(error_msg)
            return
        
        # Generar identificador único para esta apuesta
        visitor = bet_info.get('visitor', '')
        home = bet_info.get('home', '')
        bet_id = f"{bet_info.get('id', '')}_{visitor}_{home}"
        
        # Si ya se procesó anteriormente, saltar
        if bet_id in processed_bets:
            logger.info(f"Apuesta {bet_id} ya fue procesada anteriormente. Saltando.")
            return
        
        # Obtener datos del partido
        result = get_game_data(bet_info)
        
        if result.get("error"):
            handle_error_result(result, bet_id)
            return
            
        # Añadir información de la apuesta al resultado
        result = add_bet_info_to_result(result, bet_info)
        
        # Enviar resultado a Telegram
        logger.info(f"Enviando actualización a Telegram para apuesta {bet_id}")
        send_telegram_message(result)
        
        # Marcar como procesada
        processed_bets.add(bet_id)
        logger.info(f"Apuesta {bet_id} procesada exitosamente y marcada como completada")
        
    except Exception as e:
        logger.error(f"Error procesando la apuesta: {str(e)}")
        error_msg = {"error": f"Error procesando la apuesta: {str(e)}"}
        send_telegram_message(error_msg)

def handle_error_result(result: Dict[str, Any], bet_id: str) -> None:
    """
    Maneja resultados de error decidiendo si enviarlos a Telegram.
    
    Args:
        result (Dict[str, Any]): Resultado con error.
        bet_id (str): ID único de la apuesta.
    """
    error_message = result["error"]
    
    # Lista de errores que NO queremos enviar a Telegram
    ignore_errors = [
        "not found in settled yet",
        "No match found for teams",
        "found in settled but has no periods yet"
    ]
    
    # Verificar si el error debe ser ignorado para Telegram
    should_ignore = any(ignore_text in error_message for ignore_text in ignore_errors)
    
    if should_ignore:
        # Solo registrar en el log
        logger.warning(f"Error ignorado para Telegram: {error_message}")
    else:
        # Enviar a Telegram errores importantes
        logger.warning(f"Error para apuesta {bet_id}: {error_message}")
        send_telegram_message(result)

def add_bet_info_to_result(result: Dict[str, Any], bet_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Añade la información de la apuesta al resultado.
    
    Args:
        result (Dict[str, Any]): Resultado del partido.
        bet_info (Dict[str, Any]): Información de la apuesta.
        
    Returns:
        Dict[str, Any]: Resultado enriquecido con información de la apuesta.
    """
    # Información básica de la apuesta
    result["bet_info"] = {
        "id": bet_info.get('id'),
        "sport": bet_info.get('sport'),
        "league": bet_info.get('original_league', bet_info.get('league')),
        "bet_type": bet_info.get('bet_type'),
        "the_bet": bet_info.get('the_bet'),
        "line": bet_info.get('line'),
        "period": bet_info.get('period'),
        "visitor": bet_info.get('original_visitor', bet_info.get('visitor')),
        "home": bet_info.get('original_home', bet_info.get('home')),
        # Equipos reales según la API
        "actual_visitor": result.get("teams", {}).get("away", {}).get("name", ""),
        "actual_home": result.get("teams", {}).get("home", {}).get("name", ""),
        # Resultados
        "visitor_score": result.get("teams", {}).get("away", {}).get("score"),
        "home_score": result.get("teams", {}).get("home", {}).get("score")
    }
    
    # Añadir detalles por periodo si están disponibles
    periods_data = result.get("periods", [])
    if periods_data:
        result["bet_info"]["periods_detail"] = {}
        
        for period in periods_data:
            period_number = period.get("number")
            if period_number is not None:
                period_key = f"period_{period_number}"
                
                away_team = result.get("teams", {}).get("away", {}).get("name", "")
                home_team = result.get("teams", {}).get("home", {}).get("name", "")
                
                result["bet_info"]["periods_detail"][period_key] = {
                    "away_score": period.get(away_team),
                    "home_score": period.get(home_team),
                    "settled_at": period.get("settledAt")
                }
    
    return result

# ===================== FUNCIÓN PRINCIPAL =====================
def main() -> None:
    """
    Función principal que inicia el tracker de apuestas.
    """
    global SPORTS_MAPPING, last_game_ids
    
    # Inicializar entorno
    if not initialize_environment():
        logger.critical("Error inicializando el entorno. Saliendo...")
        sys.exit(1)
    
    logger.info("Bot iniciado. Leyendo apuestas desde %s", JSON_INPUT_FILE)
    
    # Cargar mapeos y datos de caché
    SPORTS_MAPPING = load_sports_mapping()
    last_game_ids = load_game_ids()
    logger.info(f"IDs de juegos cargados: {len(last_game_ids)} IDs disponibles")
    
    # Enviar mensaje de inicio
    try:
        send_telegram_message({"info": f"Bot iniciado. Monitoreando archivo {JSON_INPUT_FILE}"})
    except Exception as e:
        logger.error(f"No se pudo enviar mensaje de inicio: {e}")
    
    # Control de errores consecutivos
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    # Bucle principal
    run_main_loop(consecutive_errors, max_consecutive_errors)
    
def run_main_loop(consecutive_errors: int, max_consecutive_errors: int) -> None:
    """
    Ejecuta el bucle principal del programa.
    
    Args:
        consecutive_errors (int): Contador inicial de errores consecutivos.
        max_consecutive_errors (int): Máximo permitido de errores consecutivos.
    """
    global last_game_ids
    
    while True:
        try:
            # Leer y procesar apuestas
            bet_records = read_bets_from_json()
            
            if not bet_records:
                logger.info(f"No hay apuestas en {JSON_INPUT_FILE} o el archivo está vacío.")
            else:
                logger.info(f"Se encontraron {len(bet_records)} apuestas en {JSON_INPUT_FILE}")
                
                for bet_record in bet_records:
                    bet_info = map_bet_info(bet_record)
                    
                    if not bet_info:
                        continue
                    
                    if not bet_info.get('visitor') and not bet_info.get('home'):
                        logger.warning(f"No se pudo determinar información de equipos para la apuesta ID {bet_info.get('id', 'N/A')}.")
                        continue
                    
                    process_bet_info(bet_info)
            
            # Guardar caché
            save_game_ids(last_game_ids)
            
            # Resetear contador de errores
            consecutive_errors = 0
            
        except KeyboardInterrupt:
            handle_shutdown("Programa detenido por el usuario.")
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error en el loop principal (intento {consecutive_errors}): {e}")
            
            # Reiniciar si hay demasiados errores
            if consecutive_errors >= max_consecutive_errors:
                handle_restart(consecutive_errors)
                consecutive_errors = 0
        
        # Esperar antes de la próxima verificación
        try:
            logger.info("Esperando 60 segundos antes de la siguiente verificación...")
            time.sleep(60)
        except KeyboardInterrupt:
            handle_shutdown("Programa detenido por el usuario durante la espera.")

def handle_shutdown(message: str) -> None:
    """
    Maneja el apagado controlado del programa.
    
    Args:
        message (str): Mensaje para registrar.
    """
    logger.info(message)
    save_game_ids(last_game_ids)
    sys.exit(0)


def handle_restart(consecutive_errors: int) -> None:
    """
    Maneja el reinicio del programa después de varios errores.
    
    Args:
        consecutive_errors (int): Número de errores consecutivos.
    """
    error_message = f"Bot reiniciándose después de {consecutive_errors} errores consecutivos"
    logger.critical(f"Demasiados errores consecutivos ({consecutive_errors}). Reiniciando el programa...")
    
    # Intentar enviar notificación
    send_error_notification(error_message)
    
    # Guardar estado actual
    try:
        save_game_ids(last_game_ids)
    except Exception as e:
        logger.error(f"No se pudieron guardar los IDs de juego: {e}")
    
    # Esperar antes de reiniciar
    time.sleep(5)


# Punto de entrada del programa
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"El bot se detuvo debido a un error fatal: {str(e)}"
        logger.critical(f"Error fatal que causó la terminación del programa: {e}")
        send_error_notification(error_message)
        