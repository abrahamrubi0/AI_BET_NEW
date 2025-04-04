import requests
import json
import os
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
import time

load_dotenv()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Variable global para almacenar el último ID conocido
last_game_id = None

def send_telegram_message(json_data):
    """Envía un mensaje JSON a un grupo de Telegram en formato de código."""
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    formatted_json = json.dumps(json_data, indent=4)
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"📊 *Match update:*\n```json\n{formatted_json}\n```",
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(telegram_url, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error enviando mensaje a Telegram: {str(e)}")

def get_game_data(bet_info):
    """Obtiene los datos del partido basado en la apuesta."""
    global last_game_id  # Usamos una variable global para almacenar el último ID

    sport = bet_info.get('sport')
    rotation_number = str(bet_info.get('rotation_number', ''))

    sport_mapping = {
        "Basketball": 4
    }
    
    sport_id = sport_mapping.get(sport)
    if not sport_id:
        return {"error": f"Sport '{sport}' not recognized."}
    
    auth = HTTPBasicAuth(username, password)
    
    fixtures_url = f"https://api.ps3838.com/v3/fixtures?sportId={sport_id}"
    settled_url = f"https://api.ps3838.com/v3/fixtures/settled?sportId={sport_id}"

    try:
        # PASO 1: Buscar el partido en fixtures usando rotNum
        fixtures_response = requests.get(fixtures_url, auth=auth)
        fixtures_response.raise_for_status()
        fixtures_data = fixtures_response.json()

        game_id = None
        home_team = None
        away_team = None

        for league_info in fixtures_data.get('league', []):
            for event in league_info.get('events', []):
                if str(event.get('rotNum')) == rotation_number:
                    game_id = event.get('id')
                    home_team = event.get('home')
                    away_team = event.get('away')
                    last_game_id = game_id  # Guardar el último ID conocido
                    break

        if not game_id and last_game_id:
            print(f"⚠️ Partido con rotNum '{rotation_number}' ya no está en fixtures. Buscando en settled con ID {last_game_id}...")
            return search_in_settled(settled_url, auth, last_game_id, rotation_number)

        if not game_id:
            return {"error": f"No match found with rotNum '{rotation_number}' in fixtures and no stored ID."}

        # PASO 2: Buscar en settled usando el ID obtenido
        return search_in_settled(settled_url, auth, game_id, rotation_number, home_team, away_team)

    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"error": f"Error inesperado: {str(e)}"}

def search_in_settled(settled_url, auth, game_id, rotation_number, home_team=None, away_team=None):
    """Busca el partido en settled usando el ID del evento o el rotNum."""
    try:
        settled_response = requests.get(settled_url, auth=auth)
        settled_response.raise_for_status()
        settled_data = settled_response.json()

        for league_result in settled_data.get('leagues', []):
            for event_result in league_result.get('events', []):
                if event_result.get('id') == game_id:
                    return format_result(event_result, home_team, away_team)

        return {"error": f"Match with ID '{game_id}' not found in settled yet."}

    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"error": f"Error inesperado: {str(e)}"}

def format_result(event_result, home_team, away_team):
    """Formatea los datos del partido incluyendo períodos, score final y nombres de equipos."""
    game_id = event_result.get('id')
    periods = event_result.get('periods', [])

    result = {
        "game_id": game_id,
        "teams": {
            "home": {"name": home_team, "score": None},
            "away": {"name": away_team, "score": None}
        },
        "periods": []
    }

    final_score = next((p for p in periods if p.get('number') == 0), None)

    for period in periods:
        result["periods"].append({
            "number": period.get('number'),
            home_team: period.get('team2Score'),  # Puntaje del equipo local
            away_team: period.get('team1Score'),  # Puntaje del equipo visitante
            "settled_at": period.get('settledAt')
        })

    # Si encontramos el período final (number: 0), asignamos el score final
    if final_score:
        result["teams"]["away"]["score"] = final_score.get('team1Score')
        result["teams"]["home"]["score"] = final_score.get('team2Score')
    
    return result

bet_info = {
  "sport": "Basketball",
  "rotation_number": 539,
  "league": "NBA",
  "bet": "philadelphia 76ers u229.5",
  "side_bet": "Under",
  "handicap": "229.5",
  "price": "-110",
  "source": "MTA",
  "period": "Full Game",
  "bet_type": "Total",
  "teams": {
    "visitor": "philadelphia 76ers",
    "home": ""
  },
  "date": ""
}

# Loop infinito para ejecutar cada minuto
while True:
    try:
        result = get_game_data(bet_info)

        if result.get("error"):
            print("⚠️ Error detectado:", result["error"])
            send_telegram_message(result)  # Enviar error como JSON
            time.sleep(60)
            continue  # Sigue corriendo

        # Enviar resultado a Telegram en formato JSON
        send_telegram_message(result)

    except Exception as e:
        print(f"Error en el loop principal: {e}")

    time.sleep(60)  # Espera un minuto
