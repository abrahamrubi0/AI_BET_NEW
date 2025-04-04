# utils/environment.py
import os
from dotenv import dotenv_values
from typing import Optional

def load_environment_variables(env_file: str = ".env") -> dict:
    """
    Carga variables de entorno desde el archivo .env y retorna un dict.
    """
    return dotenv_values(env_file)

def get_critical_var(env_dict: dict, key: str) -> Optional[str]:
    """
    Obtiene una variable crítica del diccionario de entorno.
    Lanza un error si la variable no está presente.
    """
    value = env_dict.get(key)
    if not value:
        raise ValueError(f"Variable de entorno faltante o vacía: {key}")
    return value
