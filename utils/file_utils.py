# utils/file_utils.py
import json
import os
from typing import Any, Dict, Optional
from .logger import get_logger

logger = get_logger(__name__)

def load_json_file(filepath: str) -> Any:
    """Lee un archivo JSON y retorna su contenido. Devuelve None si hay errores."""
    if not os.path.exists(filepath):
        logger.warning(f"Archivo no encontrado: {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo {filepath}: {e}")
        return None

def save_json_file(filepath: str, data: Any) -> bool:
    """Guarda data en un archivo JSON. Retorna True si ok, False en caso de error."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error guardando {filepath}: {e}")
        return False
