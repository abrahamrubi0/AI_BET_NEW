# services/team_normalization_service.py

import re
from typing import List
from utils.logger import get_logger

# 1) Importar los diccionarios que necesitas desde teams.py
from teams import (
    nfl_teams,
    nba_teams,
    cfl_teams_dict,
    ncaa_football_teams,
    ncaa_basketball_teams,
    mlb_teams,
    wnba_teams,
    nhl_teams
)

logger = get_logger(__name__)

def get_team_dictionary(sport: str) -> dict:
    """
    Retorna el diccionario apropiado de equipos según el deporte indicado.
    sport: 'nfl', 'nba', 'cfl', 'ncaaf', 'ncaab', 'ncaam', 'mlb', 'wnba', 'nhl', etc.
    """
    sport = sport.lower().strip()
    if sport == "nfl":
        return nfl_teams
    elif sport == "nba":
        return nba_teams
    elif sport == "cfl":
        return cfl_teams_dict
    elif sport == "ncaaf":
        return ncaa_football_teams
    elif sport in ["ncaab", "ncaam"]:
        return ncaa_basketball_teams
    elif sport == "mlb":
        return mlb_teams
    elif sport == "wnba":
        return wnba_teams
    elif sport == "nhl":
        return nhl_teams
    else:
        # Si el deporte no coincide con ninguno, devolvemos un diccionario vacío
        logger.warning(f"Deporte no reconocido: {sport}, se retorna un dict vacío.")
        return {}

def get_normalized_team(team_name: str, league: str) -> str:
    """
    Retorna el nombre normalizado de un equipo dada la liga (deporte).
    
    - Si no existe un match exacto en el diccionario, retornamos el nombre original.
    - El diccionario se selecciona con base en 'league', que típicamente será 'nfl', 'nba', etc.
    """
    if not team_name:
        return ""
    dictionary = get_team_dictionary(league)
    return dictionary.get(team_name.lower().strip(), team_name)

def extract_team_names_from_bet(the_bet: str, league: str = "nba") -> List[str]:
    """
    Dada la descripción de una apuesta (the_bet), intenta extraer el nombre de un equipo 
    como aproximación. Esto es un ejemplo muy simple. Ajusta la regex a tu necesidad real.
    """
    the_bet = (the_bet or "").lower().strip()
    if not the_bet:
        return []
    
    # Ejemplo: tomamos la primera "palabra" (sin números ni símbolos) como posible equipo
    match = re.search(r'^([a-z]+)', the_bet)
    extracted = match.group(1) if match else None
    
    if extracted:
        normalized = get_normalized_team(extracted, league)
        return [normalized] if normalized else [extracted]
    return []
