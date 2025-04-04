import requests
import json
import os
import time
import re
import pathlib
import sys
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from datetime import datetime

# Importar diccionarios de equipos
try:
    from teams import nba_teams
    teams_imported = True
except ImportError:
    teams_imported = False
    nba_teams = {}
    print("ADVERTENCIA: No se pudo importar teams.py. Se usarán valores predeterminados.")

# Configuración de manejo de errores
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ps3838_tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno de manera segura
try:
    load_dotenv()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    
    # Verificar variables críticas
    if not all([TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, username, password]):
        logger.error("Faltan variables de entorno necesarias. Por favor verifica tu archivo .env")
        sys.exit(1)
except Exception as e:
    logger.error(f"Error al cargar variables de entorno: {e}")
    sys.exit(1)

# Nombre del archivo JSON de entrada
JSON_INPUT_FILE = "bets_today.json"
SPORTS_JSON_FILE = "sports_ps3838.json"
GAME_IDS_CACHE_FILE = "game_ids_cache.json"  # Nuevo archivo para persistir los IDs de juegos

# Variables globales con inicialización segura
last_game_ids = {}  # Formato: {'team1_team2': game_id}
active_bets = {}
processed_bets = set()
SPORTS_MAPPING = {}

# Mapeo de nombres de ligas de tus apuestas a nombres de ligas en la API
LEAGUE_MAPPING = {
    "NCAAB": "NCAA"
}

# Cargar IDs de juegos guardados desde el archivo
def load_game_ids():
    """Carga los IDs de juegos guardados desde el archivo JSON."""
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

# Guardar IDs de juegos en el archivo
def save_game_ids(game_ids):
    """Guarda los IDs de juegos en el archivo JSON."""
    try:
        with open(GAME_IDS_CACHE_FILE, 'w') as f:
            json.dump(game_ids, f)
        logger.info(f"Guardados {len(game_ids)} IDs de juegos en el archivo de caché")
    except Exception as e:
        logger.error(f"Error guardando IDs de juegos: {e}")

# Cargar el archivo de mapeo de deportes desde sports_ps3838.json
def load_sports_mapping():
    """Carga el mapeo de deportes desde el archivo JSON"""
    try:
        if not os.path.exists(SPORTS_JSON_FILE):
            logger.warning(f"Archivo de deportes no encontrado: {SPORTS_JSON_FILE}")
            return {"Basketball": 4}  # Valor por defecto
        
        with open(SPORTS_JSON_FILE, 'r') as f:
            sports_data = json.load(f)
        
        # Crear un diccionario para acceso rápido por nombre
        sports_mapping = {}
        for sport in sports_data.get('sports', []):
            if isinstance(sport, dict) and 'name' in sport and 'id' in sport:
                sports_mapping[sport.get('name')] = sport.get('id')
                # También guardar versiones en minúsculas para búsquedas insensibles a mayúsculas
                sports_mapping[sport.get('name').lower()] = sport.get('id')
        
        if not sports_mapping:
            logger.warning("No se encontraron deportes en el archivo")
            return {"Basketball": 4}  # Valor por defecto
            
        logger.info(f"Deportes cargados: {len(sports_mapping)//2} deportes disponibles")
        return sports_mapping
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar el archivo de deportes: {e}")
        return {"Basketball": 4}  # Valor por defecto
    except Exception as e:
        logger.error(f"Error cargando el archivo de deportes: {e}")
        return {"Basketball": 4}  # Valor por defecto

def send_telegram_message(json_data):
    """Envía un mensaje JSON a un grupo de Telegram en formato de código."""
    try:
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        formatted_json = json.dumps(json_data, indent=4, default=str)  # default=str para manejar objetos no serializables
        
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"📊 *Match update:*\n```json\n{formatted_json}\n```",
            "parse_mode": "Markdown"
        }
        
        response = requests.post(telegram_url, json=payload, timeout=10)  # Añadir timeout
        response.raise_for_status()
        logger.info(f"Mensaje enviado a Telegram: {json_data.get('game_id', 'N/A')}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a Telegram: {str(e)}")
    except Exception as e:
        logger.error(f"Error inesperado al enviar mensaje a Telegram: {str(e)}")

def read_bets_from_json():
    """Lee las apuestas del archivo JSON de manera segura."""
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

# Mejora 1: Actualizar la función get_normalized_team para manejar más diccionarios de ligas

def get_normalized_team(team_name, league="NBA"):
    """Obtiene el nombre normalizado del equipo usando el diccionario correspondiente."""
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

# Mejora 2: Función para verificar equipos antes de hacer peticiones

def normalize_and_verify_teams(bet_info):
    """
    Normaliza y verifica los nombres de equipos en bet_info usando teams.py
    antes de hacer peticiones a la API.
    
    Devuelve una versión actualizada de bet_info con nombres normalizados
    y una lista de nombres de equipos para búsqueda.
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
    if league.upper() in ["NCAAB", "NCAA BASKETBALL", "NCAA"]:
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

# Mejora 3: Actualizar map_bet_info para usar las mejoras

def map_bet_info(bet_record):
    """Mapea los datos del registro de apuesta a la estructura esperada."""
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

def get_league_id(sport, league):
    """
    Dado un nombre de deporte y una liga, obtiene el ID de la liga desde el archivo JSON correspondiente.
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


def get_game_data(bet_info):
    """Obtiene los datos del partido basado en la información de equipos sin importar si son home o away."""
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
        
        # Obtener el ID del deporte del sport o la league
        sport_id = SPORTS_MAPPING.get(sport) or SPORTS_MAPPING.get(sport.lower())
        
        # Si no encuentra, intentar con league
        if not sport_id:
            sport_id = SPORTS_MAPPING.get(league) or SPORTS_MAPPING.get(league.lower())
            
        # Fallback a Basketball
        if not sport_id:
            sport_id = 4  # Basketball por defecto
            logger.warning(f"No se encontró ID para '{sport}' o '{league}', usando Basketball (4)")
        
        auth = HTTPBasicAuth(username, password)
        league_id = get_league_id(sport, league)
        if league_id:
            fixtures_url = f"https://api.ps3838.com/v3/fixtures?sportId={sport_id}&leagueIds={league_id}"
        else:
            fixtures_url = f"https://api.ps3838.com/v3/fixtures?sportId={sport_id}"

        #fixtures_url = f"https://api.ps3838.com/v3/fixtures?sportId={sport_id}"
        settled_url = f"https://api.ps3838.com/v3/fixtures/settled?sportId={sport_id}"

        # PARTE 1: PRIORIZAR LA BÚSQUEDA EN IDS GUARDADOS
        logger.info("PASO 1: Revisando IDs guardados de partidos para estos equipos")
        possible_game_ids = []
        bet_id_found = False
        
        # Si hay un campo 'id' específico en bet_info, priorizarlo
        if bet_info.get('id'):
            bet_id = bet_info.get('id')
            logger.info(f"Usando bet_id de la apuesta: {bet_id}")
            
            # Verificar si este ID de apuesta está asociado a algún game_id en el caché
            for key, value in last_game_ids.items():
                # La clave podría ser el game_id directamente o una clave con el id de la apuesta
                if str(bet_id) == str(key) or str(bet_id) in str(key):
                    logger.info(f"Encontrado game_id para bet_id {bet_id}: {value}")
                    possible_game_ids.append(value)
                    bet_id_found = True
        
        # Generar todas las posibles combinaciones de claves para buscar IDs guardados
        for team1 in team_names:
            for team2 in team_names:
                if team1 == team2:
                    continue  # Ignorar combinaciones del mismo equipo
                    
                # Preparar la clave exactamente como se guarda (sin espacios, minúsculas)
                team_key = f"{team1}_{team2}".lower().replace(' ', '')
                
                if team_key in last_game_ids:
                    saved_game_id = last_game_ids[team_key]
                    logger.info(f"Encontrado ID guardado para equipos {team1} vs {team2}: {saved_game_id}")
                    possible_game_ids.append(saved_game_id)
        
        # Eliminar duplicados de IDs (un mismo ID puede estar asociado a varias combinaciones)
        unique_game_ids = list(set(possible_game_ids))
        logger.info(f"IDs únicos encontrados en caché: {unique_game_ids}")
        
        # BUSCAR EN SETTLED USANDO CADA ID GUARDADO
        for game_id in unique_game_ids:
            logger.info(f"Verificando directamente en settled el partido con ID: {game_id}")
            # Intentar buscar en settled usando el ID guardado
            result = search_in_settled(settled_url, auth, game_id, None)
            
            # Si encontramos el partido en settled, devolver el resultado inmediatamente
            if not result.get("error"):
                logger.info(f"¡ÉXITO! Partido encontrado en settled usando ID guardado: {game_id}")
                return result
            elif "not found in settled yet" in result.get("error", ""):
                logger.info(f"Partido con ID {game_id} aún no está en settled, continuando búsqueda...")
            else:
                logger.warning(f"Error al buscar partido con ID {game_id}: {result.get('error')}")
        
        # PARTE 2: SI NO ENCONTRAMOS EN SETTLED, INTENTAR FIXTURES
        logger.info("PASO 2: Buscando partidos en fixtures")
        
        # Variable para guardar el ID encontrado
        game_id = None
        home_team_full = None
        away_team_full = None
        rotation_number = None
        fixtures_data = None
        
        # Variable para indicar si tuvimos error 429 en fixtures
        fixtures_429_error = False
        
        try:
            # Primero, intentar buscar usando los IDs guardados en fixtures
            if unique_game_ids:
                fixtures_response = requests.get(fixtures_url, auth=auth, timeout=30)
                fixtures_response.raise_for_status()
                fixtures_data = fixtures_response.json()
                
                for league_info in fixtures_data.get('league', []):
                    for event in league_info.get('events', []):
                        if event.get('id') in unique_game_ids:
                            # Encontramos el partido en fixtures usando un ID guardado
                            game_id = event.get('id')
                            home_team_full = event.get('home')
                            away_team_full = event.get('away')
                            rotation_number = event.get('rotNum')
                            logger.info(f"Partido encontrado en fixtures usando ID guardado: {game_id}, {away_team_full} @ {home_team_full}")
                            break
                    if game_id:
                        break
            
            # Si no encontramos el partido usando IDs guardados, buscar por nombres de equipos
            if not game_id:
                if not fixtures_data:  # Si no se obtuvo antes
                    fixtures_response = requests.get(fixtures_url, auth=auth, timeout=30)
                    fixtures_response.raise_for_status()
                    fixtures_data = fixtures_response.json()

                for league_info in fixtures_data.get('league', []):
                    # Si es NCAAB o NCAAF, necesitamos verificar si la liga en la API comienza con "NCAA"
                    api_league_name = league_info.get('name', '').upper()
                    
                    # Ser más específico con las coincidencias de ligas para distinguir NCAA de WNCAA
                    ncaa_case = league.upper() in ["NCAAB", "NCAA BASKETBALL", "NCAA", "NCAA FOOTBALL", "NCAAF"]
                    league_match = False
                    
                    if ncaa_case:
                        # Para NCAA masculino, rechazar cualquier liga que contenga WNCAA o Women
                        if ("WNCAA" in api_league_name or "WOMEN" in api_league_name):
                            logger.debug(f"Saltando liga femenina {api_league_name}, buscando NCAA masculino")
                            continue
                            
                        # Aceptar ligas que contengan NCAA pero no WNCAA
                        if "NCAA" in api_league_name:
                            league_match = True
                        # También aceptar ligas con "COLLEGE BASKETBALL" para NCAA
                        elif "COLLEGE" in api_league_name and "BASKETBALL" in api_league_name:
                            league_match = True
                    else:
                        # Para ligas regulares, comprobar coincidencia exacta
                        if league == api_league_name or league == league_info.get('name'):
                            league_match = True
                    
                    if not league_match:
                        logger.debug(f"Saltando liga {league_info.get('name')}, buscando {league}")
                        continue
                        
                    for event in league_info.get('events', []):
                        # Registrar explícitamente liga para depuración
                        logger.info(f"Analizando partido en liga: {league_info.get('name')} (ID: {league_info.get('id')})")
                        
                        # Obtener nombres para comparar (convertir a minúsculas)
                        api_home = event.get('home', '').lower()
                        api_away = event.get('away', '').lower()
                        
                        match_found = False
                        
                        # VERIFICACIÓN EXACTA - Coincidencia exacta con cualquier equipo
                        for team_name in team_names:
                            if team_name == api_home or team_name == api_away:
                                logger.info(f"✅ Coincidencia EXACTA: '{team_name}' con home='{api_home}' o away='{api_away}'")
                                match_found = True
                                break
                        
                        # Comparaciones más flexibles para NCAA y otros casos
                        if not match_found:
                            for team_name in team_names:
                                is_ncaa = league.upper() in ["NCAAB", "NCAA BASKETBALL", "NCAA", "NCAA FOOTBALL", "NCAAF"]
                                
                                # Comparación flexible para NCAA
                                if is_ncaa:
                                    # Para NCAA, necesitamos más flexibilidad
                                    api_away_words = api_away.split()
                                    api_home_words = api_home.split()
                                    team_name_words = team_name.split()
                                    
                                    # Verificar coincidencia al inicio
                                    if (api_away.startswith(team_name) or api_home.startswith(team_name)):
                                        logger.info(f"Coincidencia NCAA (inicio): {team_name} coincide con home={api_home} o away={api_away}")
                                        match_found = True
                                        break
                                    # Verificar coincidencia como palabra individual
                                    elif (team_name in api_away_words or team_name in api_home_words):
                                        logger.info(f"Coincidencia NCAA (palabra): {team_name} coincide con home={api_home} o away={api_away}")
                                        match_found = True
                                        break
                                    # Para nombres compuestos
                                    elif len(team_name_words) > 1:
                                        # Verificar en away
                                        if len(api_away_words) >= len(team_name_words):
                                            if all(team_name_words[i] == api_away_words[i] for i in range(len(team_name_words))):
                                                logger.info(f"Coincidencia NCAA (palabras múltiples en away): {team_name} coincide con {api_away}")
                                                match_found = True
                                                break
                                        # Verificar en home
                                        if len(api_home_words) >= len(team_name_words):
                                            if all(team_name_words[i] == api_home_words[i] for i in range(len(team_name_words))):
                                                logger.info(f"Coincidencia NCAA (palabras múltiples en home): {team_name} coincide con {api_home}")
                                                match_found = True
                                                break
                                else:
                                    # Para otras ligas, comparación regular
                                    if (team_name in api_away or api_away in team_name or 
                                        team_name in api_home or api_home in team_name):
                                        logger.info(f"Coincidencia de equipo: {team_name} coincide con home={api_home} o away={api_away}")
                                        match_found = True
                                        break
                        
                        if match_found:
                            game_id = event.get('id')
                            home_team_full = event.get('home')
                            away_team_full = event.get('away')
                            rotation_number = event.get('rotNum')
                            
                            # Guardar ID por combinaciones de equipos para futuras referencias
                            api_home_lower = api_home.replace(' ', '')
                            api_away_lower = api_away.replace(' ', '')
                            
                            # Guardar combinaciones de los nombres de la API
                            team_key1 = f"{api_away_lower}_{api_home_lower}".lower()
                            team_key2 = f"{api_home_lower}_{api_away_lower}".lower()
                            last_game_ids[team_key1] = game_id
                            last_game_ids[team_key2] = game_id
                            
                            # También guardar con el ID de la apuesta si está disponible
                            if bet_info.get('id'):
                                bet_id_key = f"bet_{bet_info.get('id')}"
                                last_game_ids[bet_id_key] = game_id
                                logger.info(f"Guardando ID {game_id} para bet_id {bet_info.get('id')}")
                            
                            # También guardar combinaciones con los nombres normalizados
                            for team1 in team_names:
                                for team2 in team_names:
                                    if team1 != team2:  # Evitar guardar el mismo equipo
                                        team_key = f"{team1}_{team2}".lower().replace(' ', '')
                                        last_game_ids[team_key] = game_id
                            
                            # Guardar los IDs en el archivo para persistencia
                            save_game_ids(last_game_ids)
                            
                            logger.info(f"Partido encontrado: {away_team_full} @ {home_team_full}, ID={game_id}, RotNum={rotation_number}")
                            break
                    
                    if game_id:
                        break
                
        except requests.exceptions.HTTPError as e:
            # Capturar específicamente el error 429 (Too Many Requests)
            if "429" in str(e):
                logger.error(f"Error 429 (Too Many Requests) al acceder a fixtures: {str(e)}")
                fixtures_429_error = True
                
                # Si tenemos IDs guardados, intentar usar el primero directamente en settled
                if unique_game_ids:
                    game_id = unique_game_ids[0]
                    logger.info(f"Usando ID guardado {game_id} debido a error 429 en fixtures")
            else:
                # Otros errores HTTP
                logger.error(f"Error HTTP en fixtures: {str(e)}")
                return {"error": f"Error HTTP: {str(e)}"}
        except requests.exceptions.RequestException as e:
            # Otros errores de conexión
            logger.error(f"Error de conexión en fixtures: {str(e)}")
            
            # Si tenemos IDs guardados, intentar usar el primero
            if unique_game_ids:
                game_id = unique_game_ids[0]
                logger.info(f"Usando ID guardado {game_id} debido a error de conexión en fixtures")
            else:
                return {"error": f"Error de conexión: {str(e)}"}

        # PARTE 3: SI NO ENCONTRAMOS EL PARTIDO EN FIXTURES O HUBO ERROR 429, USAR IDS GUARDADOS
        if (not game_id and unique_game_ids) or fixtures_429_error:
            if not game_id and unique_game_ids:
                game_id = unique_game_ids[0]  # Usar el primer ID guardado encontrado
            
            logger.info(f"{'Error 429 detectado, u' if fixtures_429_error else 'No se encontró partido en fixtures. U'}sando ID guardado: {game_id} para buscar en settled")
            
            # IMPORTANTE: Aun sin tener información completa, intentar buscar en settled
            return search_in_settled(settled_url, auth, game_id, None)
        
        # Si no encontramos el partido ni en fixtures ni en IDs guardados
        if not game_id:
            # Para NCAA, mostrar equipos disponibles para ayudar a diagnosticar
            if fixtures_data and league.upper() in ["NCAAB", "NCAA BASKETBALL", "NCAA", "NCAA FOOTBALL", "NCAAF"]:
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
            
            team_names_str = ", ".join(team_names)
            logger.info(f"No se encontró partido para {team_names_str} en fixtures ni IDs guardados.")
            return {"error": f"No match found for teams {team_names_str} in fixtures."}

        # PARTE 4: SI ENCONTRAMOS EL PARTIDO EN FIXTURES, BUSCAR EN SETTLED
        return search_in_settled(settled_url, auth, game_id, rotation_number, home_team_full, away_team_full)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión general: {str(e)}")
        
        # Si tenemos IDs guardados, intentar usar el primero directamente
        possible_game_ids = []
        
        # Generar todas las posibles combinaciones de claves para buscar IDs guardados
        for team1 in team_names:
            for team2 in team_names:
                if team1 == team2:
                    continue  # Ignorar combinaciones del mismo equipo
                    
                # Preparar la clave exactamente como se guarda (sin espacios, minúsculas)
                team_key = f"{team1}_{team2}".lower().replace(' ', '')
                
                if team_key in last_game_ids:
                    saved_game_id = last_game_ids[team_key]
                    possible_game_ids.append(saved_game_id)
        
        # Eliminar duplicados de IDs
        unique_game_ids = list(set(possible_game_ids))
        
        if unique_game_ids:
            game_id = unique_game_ids[0]
            logger.info(f"Usando ID guardado {game_id} debido a error de conexión general")
            return search_in_settled(settled_url, auth, game_id, None)
            
        return {"error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error(f"Error inesperado en get_game_data: {str(e)}")
        return {"error": f"Error inesperado: {str(e)}"}

# Función mejorada para buscar en settled
def search_in_settled(settled_url, auth, game_id, rotation_number, home_team=None, away_team=None):
    """Busca el partido en settled usando el ID del evento."""
    try:
        logger.info(f"Buscando partido con ID {game_id} en settled")
        
        settled_response = requests.get(settled_url, auth=auth, timeout=30)
        settled_response.raise_for_status()
        settled_data = settled_response.json()

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

# Función para procesar apuestas (modificada para no enviar ciertos errores a Telegram)
def process_bet_info(bet_info):
    """Procesa una apuesta y envía los resultados de manera segura."""
    if not bet_info or not isinstance(bet_info, dict):
        return
    
    try:
        # Verificar si tiene los campos necesarios (al menos uno de los equipos)
        if (not bet_info.get('visitor') and not bet_info.get('home')) or not bet_info.get('sport'):
            error_msg = {"error": f"JSON inválido para la apuesta ID {bet_info.get('id', 'N/A')}. Debe contener información de al menos un equipo y deporte."}
            logger.warning(error_msg['error'])
            send_telegram_message(error_msg)
            return
        
        # Generar un identificador único para esta apuesta
        visitor = bet_info.get('visitor', '')
        home = bet_info.get('home', '')
        bet_id = f"{bet_info.get('id', '')}_{visitor}_{home}"
        
        # Si ya hemos procesado esta apuesta con éxito anteriormente, no volver a procesar
        if bet_id in processed_bets:
            logger.info(f"Apuesta {bet_id} ya fue procesada anteriormente. Saltando.")
            return
        
        result = get_game_data(bet_info)
        
        if result.get("error"):
            error_message = result["error"]
            
            # Lista de errores que NO queremos enviar a Telegram
            ignore_errors = [
                "not found in settled yet",
                "No match found for teams",  # Este es el error que quieres filtrar
                "found in settled but has no periods yet"
            ]
            
            # Verificar si el error debe ser ignorado para Telegram
            should_ignore = any(ignore_text in error_message for ignore_text in ignore_errors)
            
            if should_ignore:
                # Solo registrar en el log, no enviar a Telegram
                logger.warning(f"Error ignorado para Telegram: {error_message}")
            else:
                # Enviar a Telegram errores importantes
                logger.warning(f"Error para apuesta {bet_id}: {error_message}")
                send_telegram_message(result)
            
            return
            
        # Si llegamos aquí, hemos encontrado información válida
        # Añadir la información original de la apuesta al resultado
        result["bet_info"] = {
            "id": bet_info.get('id'),
            "sport": bet_info.get('sport'),
            "league": bet_info.get('original_league', bet_info.get('league')),  # Usar la liga original
            "bet_type": bet_info.get('bet_type'),
            "the_bet": bet_info.get('the_bet'),
            "line": bet_info.get('line'),
            "period": bet_info.get('period'),  # Incluir el periodo
            "visitor": bet_info.get('original_visitor', bet_info.get('visitor')),
            "home": bet_info.get('original_home', bet_info.get('home')),
            # Añadir información de los equipos reales según la API
            "actual_visitor": result.get("teams", {}).get("away", {}).get("name", ""),
            "actual_home": result.get("teams", {}).get("home", {}).get("name", ""),
            # Añadir resultados de cada equipo
            "visitor_score": result.get("teams", {}).get("away", {}).get("score"),
            "home_score": result.get("teams", {}).get("home", {}).get("score")
        }
        
        # También añadir información de resultados por periodo si está disponible
        periods_data = result.get("periods", [])
        if periods_data:
            result["bet_info"]["periods_detail"] = {}
            
            # Procesar cada periodo y añadir al resultado
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
        
        # Enviar resultado a Telegram
        logger.info(f"Enviando actualización a Telegram para apuesta {bet_id}")
        send_telegram_message(result)
        
        # Marcar esta apuesta como procesada con éxito
        processed_bets.add(bet_id)
        logger.info(f"Apuesta {bet_id} procesada exitosamente y marcada como completada")
        
    except Exception as e:
        logger.error(f"Error procesando la apuesta: {str(e)}")
        error_msg = {"error": f"Error procesando la apuesta: {str(e)}"}
        send_telegram_message(error_msg)

def format_result(event_result, home_team, away_team, rotation_number=None):
    """Formatea los datos del partido de manera segura."""
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

def main():
    logger.info("Bot iniciado. Leyendo apuestas desde %s", JSON_INPUT_FILE)
    
    # Cargar los deportes directamente del archivo JSON
    global SPORTS_MAPPING, last_game_ids
    SPORTS_MAPPING = load_sports_mapping()
    
    # Cargar IDs de juegos guardados
    last_game_ids = load_game_ids()
    logger.info(f"IDs de juegos cargados: {len(last_game_ids)} IDs disponibles")
    
    # Mostrar estado de importación de teams
    if teams_imported:
        logger.info("Diccionario de equipos importado correctamente")
        logger.info(f"Equipos NBA cargados: {len(nba_teams)} equipos disponibles")
    else:
        logger.warning("No se pudo importar teams.py. No hay diccionario de equipos disponible.")
    
    # Enviar mensaje de inicio
    try:
        send_telegram_message({"info": f"Bot iniciado. Monitoreando archivo {JSON_INPUT_FILE}"})
    except Exception as e:
        logger.error(f"No se pudo enviar mensaje de inicio: {e}")
    
    # Límite de errores consecutivos
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            # Leer apuestas del archivo JSON
            bet_records = read_bets_from_json()
            
            if not bet_records:
                logger.info(f"No hay apuestas en {JSON_INPUT_FILE} o el archivo está vacío.")
            else:
                logger.info(f"Se encontraron {len(bet_records)} apuestas en {JSON_INPUT_FILE}")
                
                # Procesar cada apuesta
                for bet_record in bet_records:
                    # Mapear a la estructura esperada
                    bet_info = map_bet_info(bet_record)
                    
                    # Verificar si el mapeo fue exitoso
                    if not bet_info:
                        continue
                    
                    # Verificar si tiene información de al menos un equipo
                    if not bet_info.get('visitor') and not bet_info.get('home'):
                        logger.warning(f"No se pudo determinar información de equipos para la apuesta ID {bet_info.get('id', 'N/A')}.")
                        continue
                    
                    # Procesar la apuesta
                    process_bet_info(bet_info)
            
            # Guardar IDs de juegos después de procesar todo
            save_game_ids(last_game_ids)
            
            # Resetear contador de errores después de un ciclo exitoso
            consecutive_errors = 0
            
        except KeyboardInterrupt:
            logger.info("Programa detenido por el usuario.")
            # Guardar IDs antes de salir
            save_game_ids(last_game_ids)
            sys.exit(0)
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error en el loop principal (intento {consecutive_errors}): {e}")
            
            # Si hay demasiados errores consecutivos, reiniciar el programa
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"Demasiados errores consecutivos ({consecutive_errors}). Reiniciando el programa...")
                # Enviar mensaje de reinicio a Telegram
                try:
                    send_telegram_message({"critical": f"Bot reiniciándose después de {consecutive_errors} errores consecutivos"})
                except:
                    pass
                
                # Guardar IDs antes de reiniciar
                save_game_ids(last_game_ids)
                
                # Esperar un poco antes de reiniciar
                time.sleep(5)
                consecutive_errors = 0
        
        # Esperar antes de la próxima verificación
        try:
            logger.info("Esperando 60 segundos antes de la siguiente verificación...")
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Programa detenido por el usuario durante la espera.")
            # Guardar IDs antes de salir
            save_game_ids(last_game_ids)
            sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Error fatal que causó la terminación del programa: {e}")
        try:
            send_telegram_message({"critical": f"El bot se detuvo debido a un error fatal: {str(e)}"})
        except:
            pass
        # Intentar guardar los IDs antes de terminar
        try:
            save_game_ids(last_game_ids)
        except:
            pass
        sys.exit(1)