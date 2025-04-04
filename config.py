# config.py

# Nombres de archivos
JSON_INPUT_FILE = "data/bets_today.json"
SPORTS_JSON_FILE = "data/sports_ps3838.json"
GAME_IDS_CACHE_FILE = "data/game_ids_cache.json"
SETTLED_LAST_FILE = "data/settled_last.json"
SPORTS_PS3838_PATH = "data/sports_ps3838.json"

# Mapeos predeterminados
DEFAULT_SPORTS_MAPPING = {"Basketball": 4}

LEAGUE_MAPPING = {
    "NCAAB": "NCAA"
}

NCAA_LEAGUES = ["NCAAB", "NCAA BASKETBALL", "NCAA", "NCAA FOOTBALL", "NCAAF"]

# Rutas base de la API
API_BASE_URL = "https://api.ps3838.com/v3"
FIXTURES_API_PATH = f"{API_BASE_URL}/fixtures"
SETTLED_API_PATH = f"{API_BASE_URL}/fixtures/settled"

# Tiempo de espera en segundos para el loop principal
MAIN_LOOP_SLEEP = 60
MAX_CONSECUTIVE_ERRORS = 5
