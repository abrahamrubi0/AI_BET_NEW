import json
import openai
from pathlib import Path
from dotenv import load_dotenv
import os

# Cargar API KEY
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Cargar JSON original
json_path = Path("results.json")
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Procesar cada apuesta
for bet_data in data["bets"]:
    bet = bet_data["bet_info"]
    periods = bet_data["periods"]
    home = bet.get("home", "Unknown")
    away = bet.get("visitor", "Unknown")

    prompt = f"""
You are a betting analyst AI.

The bet is:
- Type: {bet['bet_type']}
- Line: {bet.get('line', -110)}
- Bet: {bet['the_bet']}
- Period: {bet['period']}
- Home team: {home}
- Away team: {away}

Game results per period:
{json.dumps(periods, indent=2)}

Based on the bet and results, determine if the bet was won, lost, or push.
Only reply with one word: "won", "lost", or "push".
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in grading sports bets."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        result_text = response["choices"][0]["message"]["content"].strip().lower()

        # Limpiar campos anteriores si los hay
        for key in ["won", "lost", "push", "won/lost/push"]:
            bet.pop(key, None)

        # Insertar resultado como clave
        if result_text in ["won", "lost", "push"]:
            bet[result_text] = 1
            bet["has_been_graded"] = 1
            print(f"Apuesta ID {bet['id']} calificada como: {result_text.upper()}")
        else:
            print(f"Respuesta inesperada para apuesta ID {bet['id']}: {result_text}")

    except Exception as e:
        print(f"Error al calificar apuesta ID {bet['id']}: {str(e)}")

# Guardar en nuevo archivo
graded_path = Path("graded_result.json")
with open(graded_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)

print("Archivo guardado como: data/graded_result.json")