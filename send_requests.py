import json
import os
import time
import pymssql
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Datos de configuración
DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Nombre del archivo JSON de salida
JSON_OUTPUT_FILE = "data/bets_today.json"

# Función para guardar apuestas en un archivo JSON
def save_to_json(data):
    """Guarda los datos en un archivo JSON."""
    try:
        with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, indent=4, ensure_ascii=False)
        print(f"Datos guardados correctamente en {JSON_OUTPUT_FILE}")
    except Exception as e:
        print(f"Error guardando datos en JSON: {str(e)}")

# Función para obtener apuestas de la base de datos
def get_bet_requests():
    """Obtiene los registros de la base de datos con has_been_graded IS NULL y fecha de hoy."""
    try:
        conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME)
        cursor = conn.cursor(as_dict=True)
        
        today = datetime.now().strftime('%Y-%m-%d')
        query = f"""
        SELECT id, sport, league, bet_type, the_bet, line, source, handicap, side_bet, period, visitor, home 
        FROM bet_requests 
        WHERE has_been_graded IS NULL AND CAST(request_time AS DATE) = '{today}'
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        conn.close()
        return results
    except Exception as e:
        print(f"Error al obtener datos de SQL Server: {e}")
        return []

# Función principal que ejecuta el loop
def main():
    print("Script iniciado")

    while True:
        try:
            bet_requests = get_bet_requests()
            if not bet_requests:
                print("No hay nuevas apuestas para hoy.")
            else:
                print(f"Se encontraron {len(bet_requests)} apuestas para guardar.")
                # Guardar todas las apuestas en el archivo JSON
                save_to_json(bet_requests)

        except Exception as e:
            print(f"Error en el loop principal: {e}")
        
        # Esperar antes de la siguiente comprobación
        print(f"Esperando 60 segundos antes de la siguiente comprobación...")
        time.sleep(60)

# Ejecutar el programa
if __name__ == "__main__":
    main()