import json
import os
import requests
from dotenv import dotenv_values

config = dotenv_values(".env")

def obtener_ligas_por_deporte(sport_id, sport_name):
    """
    Obtiene las ligas disponibles para un deporte específico y las guarda en un archivo JSON.
    
    Args:
        sport_id (int): ID del deporte
        sport_name (str): Nombre del deporte
    
    Returns:
        bool: True si se completó con éxito, False en caso contrario
    """
    url = f"https://api.ps3838.com/v3/fixtures/settled?sportId=4&leagueIds=493&since=0{sport_id}"
    
    # Obtener credenciales del archivo .env
    username = config['USERNAME']
    password = config['PASSWORD']
    
    # Verificar si las credenciales están disponibles
    if not username or not password:
        print("Error: No se encontraron las credenciales en el archivo .env")
        return False

    try:
        # Realiza la petición GET con autenticación básica
        response = requests.get(url, auth=(username, password))
        
        # Verifica si la petición fue exitosa
        if response.status_code == 200:
            data = response.json()
            
            # Extrae solo los IDs y nombres de las ligas
            leagues = []
            if "league" in data:
                for league in data["league"]:
                    leagues.append({
                        "id": league["id"],
                        "name": league["name"]
                    })
            
            # Crea el diccionario final
            result = {
                "leagues": leagues
            }
            
            # Guarda los datos en un archivo JSON
            filename = f"{sport_name.lower()}.json"
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(result, file, indent=4, ensure_ascii=False)
            
            print(f"Se ha guardado la información de {sport_name} en {filename}")
            return True
        else:
            print(f"Error al obtener datos para {sport_name}: {response.status_code}")
            return False
    
    except Exception as e:
        print(f"Error al procesar {sport_name}: {str(e)}")
        return False

def main():
    """
    Función principal que lee los deportes de sports_ps3838.json y obtiene las ligas para cada uno.
    """
    try:
        # Verifica si existe el archivo de deportes
        if not os.path.exists("sports_ps3838.json"):
            print("No se encontró el archivo sports_ps3838.json")
            return
        
        # Lee el archivo de deportes
        with open("sports_ps3838.json", "r", encoding="utf-8") as file:
            sports_data = json.load(file)
        
        # Procesa cada deporte
        if "sports" in sports_data:
            for sport in sports_data["sports"]:
                sport_id = sport["id"]
                sport_name = sport["name"]
                print(f"Procesando {sport_name} (ID: {sport_id})...")
                obtener_ligas_por_deporte(sport_id, sport_name)
        else:
            print("No se encontraron deportes en el archivo")
    
    except Exception as e:
        print(f"Error en la ejecución principal: {str(e)}")

if __name__ == "__main__":
    main()