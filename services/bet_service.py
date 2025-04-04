# services/bet_service.py
import re
from typing import Dict, Any, List, Tuple, Optional
from config import (
    DEFAULT_SPORTS_MAPPING,
    LEAGUE_MAPPING,
    NCAA_LEAGUES,
    GAME_IDS_CACHE_FILE,
    SETTLED_LAST_FILE,
    SPORTS_JSON_FILE,
    SPORTS_PS3838_PATH
)
from utils.logger import get_logger
from utils.file_utils import load_json_file, save_json_file
from services.team_normalization_service import (
    get_normalized_team,
    extract_team_names_from_bet
)
from services.ps3838_service import (
    search_in_settled,
    get_fixtures,
    get_settled_fixtures
)

logger = get_logger(__name__)

def load_sports_mapping() -> Dict[str, int]:
    """Carga el mapeo de deportes desde sports_ps3838.json o usa valores por defecto."""
    data = load_json_file(SPORTS_JSON_FILE)
    if not data or 'sports' not in data:
        return DEFAULT_SPORTS_MAPPING

    sports_mapping = {}
    for sport in data['sports']:
        name = sport.get('name', '')
        sid = sport.get('id', 0)
        sports_mapping[name] = sid
        sports_mapping[name.lower()] = sid

    return sports_mapping if sports_mapping else DEFAULT_SPORTS_MAPPING

def get_sport_id(sport_name: str) -> int:
    """
    Obtiene el SportID a partir del nombre del deporte.
    """
    try:
        # Cargar el archivo sports_ps3838.json
        sports_data = load_json_file(SPORTS_PS3838_PATH)
        
        # Iterar por los deportes para encontrar el ID
        for sport in sports_data.get("sports", []):
            if sport.get("name") == sport_name:
                logger.info(f"SportID encontrado para {sport_name}: {sport.get('id')}")
                return sport.get("id")
        
        logger.error(f"No se encontró SportID para {sport_name}")
        return 0
    except Exception as e:
        logger.error(f"Error al obtener SportID: {str(e)}")
        return 0
    
def get_league_ids(sport_name: str, league_name: str) -> str:
    """
    Obtiene el LeagueID a partir del nombre del deporte y la liga.
    """
    try:
        # Convertir el nombre del deporte a minúsculas para el nombre del archivo
        sport_file = f"data/{sport_name.lower()}.json"
        
        # Cargar el archivo JSON específico del deporte
        league_data = load_json_file(sport_file)
        
        # Iterar por las ligas para encontrar el ID
        for league in league_data.get("leagues", []):
            if league.get("name") == league_name:
                logger.info(f"LeagueID encontrado para {league_name}: {league.get('id')}")
                return str(league.get("id"))
        
        logger.error(f"No se encontró LeagueID para {league_name}")
        return ""
    except Exception as e:
        logger.error(f"Error al obtener LeagueID: {str(e)}")
        return "" 
    
def map_bet_info(bet_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extrae los campos relevantes de un registro de apuesta y los normaliza.
    """
    try:
        if not isinstance(bet_record, dict):
            return None

        sport = bet_record.get('sport', 'Basketball').strip()
        league = bet_record.get('league', 'NBA').strip()
        normalized_league = LEAGUE_MAPPING.get(league.upper(), league)

        visitor = (bet_record.get('visitor') or "").strip().lower()
        home = (bet_record.get('home') or "").strip().lower()
        the_bet = (bet_record.get('the_bet') or "").lower()

        # Normalizar nombres con diccionarios
        normalized_visitor = get_normalized_team(visitor, league)
        normalized_home = get_normalized_team(home, league)

        return {
            "id": bet_record.get('id'),
            "sport": sport,
            "league": normalized_league,
            "original_league": league,
            "visitor": normalized_visitor,
            "home": normalized_home,
            "bet_type": bet_record.get('bet_type'),
            "the_bet": the_bet,
            "line": bet_record.get('line'),
            "period": bet_record.get('period', '')
        }
    except Exception as e:
        logger.error(f"Error al mapear bet_info: {e}")
        return None

def enrich_result_with_team_names(result: Dict[str, Any], game_id: int, fixtures_data: Dict[str, Any], bet_info: Dict[str, Any]) -> None:
    logger.info(f"[ENRICH DEBUG ID {bet_info.get('id')}] Buscando en fixtures el game_id={game_id}")
    for league_dict in fixtures_data.get('league', []):
        for event in league_dict.get('events', []):
            logger.info(f"[ENRICH DEBUG ID {bet_info.get('id')}] Revisando fixture event ID={event.get('id')} → {event.get('home')} vs {event.get('away')}")
            if int(event.get("id", 0)) == int(game_id):
                result["actual_home"] = event.get("home", "")
                result["actual_away"] = event.get("away", "")
                logger.info(f"[ENRICH Apuesta ID {bet_info.get('id')}] Insertados desde fixtures → Visitor: {event.get('away')} | Home: {event.get('home')}")
                return

def get_game_data(
    username: str,
    password: str,
    bet_info: Dict[str, Any],
    sports_mapping: Dict[str, int],
    game_ids_cache: Dict[str, str],
    last_values_cache: Dict[str, int]
) -> Dict[str, Any]:
    visitor = bet_info.get('visitor', '')
    home = bet_info.get('home', '')
    the_bet = bet_info.get('the_bet', '')
    league = bet_info.get('league', 'NBA')

    team_names = [visitor, home]
    team_names = [t for t in team_names if t]
    if not team_names:
        team_names = extract_team_names_from_bet(the_bet, league)

    if not team_names:
        return {"error": "No hay equipos para buscar el partido."}

    sport_id = get_sport_id(bet_info.get('sport', ''))
    league_ids_param = get_league_ids(bet_info.get('sport', ''), league)
    if not league_ids_param:
        league_ids_param = "493"

    possible_game_ids = []
    bet_id_key = f"bet_{bet_info.get('id')}"
    if bet_id_key in game_ids_cache:
        possible_game_ids.append(game_ids_cache[bet_id_key])

    for t1 in team_names:
        for t2 in team_names:
            if t1 != t2:
                cache_key = f"{t1}_{t2}".replace(' ', '')
                if cache_key in game_ids_cache:
                    possible_game_ids.append(game_ids_cache[cache_key])

    unique_game_ids = list(set(possible_game_ids))

    # Cargar fixtures antes de usarlos
    fixtures_data = get_fixtures(username, password, sport_id, league_ids_param)
    if "error" in fixtures_data:
        logger.warning(f"No se pudo cargar fixtures: {fixtures_data['error']}")
        fixtures_data = {"league": []}

    # 4. Buscar directamente en settled usando game_ids en caché
    for gid in unique_game_ids:
        settled_result = search_in_settled(
            username, password, sport_id, league_ids_param,
            last_values_cache, SETTLED_LAST_FILE, game_id=gid
        )
        if "error" not in settled_result:
            enriched = {
                "id": settled_result.get("id"),
                "periods": settled_result.get("periods", []),
            }
            enrich_result_with_team_names(enriched, gid, fixtures_data, bet_info)
            return enriched
                # Intentar cargar nombres reales desde fixtures/settled
        settled_fixtures = get_settled_fixtures(username, password, sport_id, league_ids_param)
        if "error" not in settled_fixtures:
            for league_dict in settled_fixtures.get('league', []):
                for event in league_dict.get('events', []):
                    if int(event.get("id", 0)) == int(gid):
                        settled_result["actual_home"] = event.get("home", "")
                        settled_result["actual_away"] = event.get("away", "")
                        logger.info(f"[SETTLED_FIXTURES ID {gid}] Nombres reales insertados → {event.get('away')} vs {event.get('home')}")
                        break

    # 5. Si no se encontró en settled por cache, buscar por nombres en fixtures
    for league_dict in fixtures_data.get('league', []):
        for event in league_dict.get('events', []):
            api_home = event.get('home', '').lower()
            api_away = event.get('away', '').lower()
            logger.info(f"[Apuesta ID {bet_info.get('id')}] Equipos de la API - Visitor: {api_away} | Home: {api_home}")

            if any(t in api_home or api_home in t for t in team_names) or \
               any(t in api_away or api_away in t for t in team_names):

                gid = event.get('id')
                game_ids_cache[f"{api_away.replace(' ','')}_{api_home.replace(' ','')}"] = gid
                game_ids_cache[f"{api_home.replace(' ','')}_{api_away.replace(' ','')}"] = gid
                if bet_id_key:
                    game_ids_cache[bet_id_key] = gid
                save_json_file(GAME_IDS_CACHE_FILE, game_ids_cache)

                settled_result = search_in_settled(
                    username, password, sport_id, league_ids_param,
                    last_values_cache, SETTLED_LAST_FILE,
                    game_id=gid
                )

                # Agregar nombres reales
                settled_result["actual_home"] = event.get("home", "")
                settled_result["actual_away"] = event.get("away", "")
                logger.info(f"[Apuesta ID {bet_info.get('id')}] Nombres reales insertados desde fixtures: Visitor: {event.get('away')} | Home: {event.get('home')}")
                return settled_result

    return {"error": "Partido no encontrado en fixtures ni en la caché."}

def add_bet_info_to_result(result: Dict[str, Any], bet_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriquecer el resultado del partido con la información de la apuesta.
    Si el resultado tiene 'actual_home' y 'actual_away', se usan esos nombres reales.
    """
    final_visitor = result.get("actual_away", bet_info.get('visitor'))
    final_home = result.get("actual_home", bet_info.get('home'))

    logger.info(f"[ADD Apuesta ID {bet_info.get('id')}] Equipos para Telegram - Visitor: {final_visitor} | Home: {final_home}")

    result["bet_info"] = {
        "id": bet_info.get('id'),
        "sport": bet_info.get('sport'),
        "league": bet_info.get('original_league', bet_info.get('league')),
        "bet_type": bet_info.get('bet_type'),
        "the_bet": bet_info.get('the_bet'),
        "line": bet_info.get('line'),
        "period": bet_info.get('period'),
        "visitor": final_visitor,
        "home": final_home
    }
    return result

def process_bet(
    username: str,
    password: str,
    bot_token: str,
    chat_id: str,
    bet_info: Dict[str, Any],
    sports_mapping: Dict[str, int],
    game_ids_cache: Dict[str, str],
    last_values_cache: Dict[str, int],
    processed_bets: set
) -> None:
    """
    Procesa una apuesta individual:
    1. Verifica si ya fue procesada.
    2. Obtiene datos del partido.
    3. Envío de resultados a Telegram si corresponde.
    """
    from services.telegram_service import send_telegram_message

    bet_id_key = f"{bet_info.get('id')}_{bet_info.get('visitor')}_{bet_info.get('home')}"
    if bet_id_key in processed_bets:
        logger.info(f"Apuesta {bet_id_key} ya procesada. Se omite.")
        return

    # Buscar los datos del partido
    result = get_game_data(
        username, password, bet_info,
        sports_mapping, game_ids_cache, last_values_cache
    )

    # Manejar errores específicos
    if "error" in result:
        if "not found in settled yet" in result["error"].lower():
            logger.info("El partido aún no aparece en 'settled'. Se ignora este error para no saturar Telegram.")
        else:
            logger.warning(f"Error al procesar {bet_id_key}: {result['error']}")
            send_telegram_message(bot_token, chat_id, result)
        return

    # Añadir información de la apuesta
    enriched_result = add_bet_info_to_result(result, bet_info)
    send_telegram_message(bot_token, chat_id, enriched_result)
    processed_bets.add(bet_id_key)
    logger.info(f"Apuesta {bet_id_key} procesada y notificada en Telegram.")
