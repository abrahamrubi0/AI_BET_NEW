# services/ps3838_service.py
import base64
import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, Any, Optional, List, Tuple
from config import SETTLED_API_PATH, FIXTURES_API_PATH
from utils.file_utils import save_json_file
from utils.logger import get_logger

logger = get_logger(__name__)

def build_api_url(base_path: str, params: Dict[str, Any]) -> str:
    """
    Construye una URL para la API a partir del path y los parámetros.
    """
    query_str = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base_path}?{query_str}"

def search_in_settled(
    username: str,
    password: str,
    sport_id: int,
    league_ids: str,
    last_values_cache: Dict[str, int],
    last_values_filepath: str,
    game_id: Optional[str] = None
) -> Dict[str, Any]:
    try:
        auth = HTTPBasicAuth(username, password)
        sport_key = str(sport_id)
        since_value = last_values_cache.get(sport_key, 0)
        
        # Validación adicional del valor since
        if not isinstance(since_value, (int, str)) or since_value < 0:
            logger.warning(f"Valor since inválido ({since_value}), usando 0")
            since_value = 0
        
        # Mejoramos el manejo del parámetro since

        params = {
            "sportId": sport_id,
            "leagueIds": league_ids,
            "since": 0
        }
        
        url = build_api_url(SETTLED_API_PATH, params)
        logger.info(f"URL de la petición: {url}")
        
        response = requests.get(url, auth=auth, timeout=30)
        
        # Mejoramos el logging de errores
        if response.status_code != 200:
            logger.error(f"Error HTTP {response.status_code}: {response.text}")
        
        response.raise_for_status()

        data = response.json()

        # Actualizar 'last' y guardar
        if 'last' in data:
            last_values_cache[sport_key] = data['last']
            save_json_file(last_values_filepath, last_values_cache)

        # Si no buscamos un game_id específico, retornamos todo
        if not game_id:
            return data

        # Buscar el evento en la respuesta
        for league in data.get('leagues', []):
            for event in league.get('events', []):
                if event.get('id') == game_id:
                    logger.info(f"Partido encontrado en settled: {game_id}")
                    return event

        return {"error": f"Partido con ID {game_id} no encontrado en settled."}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión en settled: {str(e)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Respuesta del servidor: {e.response.text}")
        return {"error": f"Error de conexión: {str(e)}"}

def get_fixtures(
    username: str,
    password: str,
    sport_id: int,
    league_ids: str
) -> Dict[str, Any]:
    """
    Obtiene el JSON de la API /fixtures para un sportId y leagueIds.
    """
    auth = HTTPBasicAuth(username, password)
    
    # Validación de parámetros
    if not sport_id or sport_id <= 0:
        logger.error(f"sport_id inválido: {sport_id}")
        return {"error": "sport_id inválido"}
        
    if not league_ids:
        logger.error("league_ids está vacío")
        return {"error": "league_ids está vacío"}
    
    params = {
        "sportId": sport_id,
        "leagueIds": league_ids,
        "isLive": 1,
        "since": 0
    }
    
    url = build_api_url(FIXTURES_API_PATH, params)
    logger.info(f"Realizando petición a fixtures con: sport_id={sport_id}, league_ids={league_ids}")
    
    try:
        response = requests.get(url, auth=auth, timeout=30)
        
        # Logging detallado
        logger.debug(f"URL de la petición: {url}")
        logger.debug(f"Código de estado: {response.status_code}")
        logger.debug(f"Headers de respuesta: {dict(response.headers)}")
        
        # Si hay contenido, mostrar los primeros 200 caracteres
        if response.text:
            logger.debug(f"Primeros 200 caracteres de la respuesta: {response.text[:200]}")
        else:
            logger.warning("La respuesta está vacía")
            
        # Verificamos el código de estado antes de procesar
        if response.status_code != 200:
            logger.error(f"Error HTTP {response.status_code}")
            logger.error(f"Respuesta completa: {response.text}")
            return {"error": f"Error HTTP {response.status_code}"}
            
        # Verificamos que la respuesta no esté vacía
        if not response.text.strip():
            logger.error("La respuesta del servidor está vacía")
            return {"error": "Respuesta vacía del servidor"}
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión en fixtures: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Respuesta del servidor: {e.response.text}")
            logger.error(f"Headers de respuesta: {dict(e.response.headers)}")
        return {"error": f"Error de conexión: {str(e)}"}
    except ValueError as e:
        logger.error(f"Error al procesar JSON: {str(e)}")
        return {"error": f"Error al procesar la respuesta: {str(e)}"}

def get_settled_fixtures(
    username: str,
    password: str,
    sport_id: int,
    league_ids: str
) -> Dict[str, Any]:
    """
    Obtiene los partidos pasados desde el endpoint /fixtures/settled (con nombres de equipos).
    """
    from config import SETTLED_API_PATH  # Asegúrate de tenerlo en config

    auth = HTTPBasicAuth(username, password)
    params = {
        "sportId": sport_id,
        "leagueIds": league_ids,
        "since": 0
    }

    url = build_api_url(SETTLED_API_PATH, params)
    logger.info(f"Realizando petición a fixtures/settled con: sport_id={sport_id}, league_ids={league_ids}")

    try:
        response = requests.get(url, auth=auth, timeout=30)
        if response.status_code != 200:
            logger.error(f"Error HTTP {response.status_code} en fixtures/settled: {response.text}")
            return {"error": f"HTTP {response.status_code}"}

        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión en fixtures/settled: {str(e)}")
        return {"error": f"Conexión fallida: {str(e)}"}
