# main.py
import sys
import time

from utils.logger import get_logger
from utils.environment import load_environment_variables, get_critical_var
from utils.file_utils import load_json_file, save_json_file
from config import (
    JSON_INPUT_FILE,
    GAME_IDS_CACHE_FILE,
    SETTLED_LAST_FILE,
    MAIN_LOOP_SLEEP,
    MAX_CONSECUTIVE_ERRORS
)
from services.bet_service import (
    map_bet_info,
    load_sports_mapping,
    process_bet
)

logger = get_logger(__name__)

def main():
    # Cargar variables de entorno
    env = load_environment_variables(".env")
    try:
        username = get_critical_var(env, "USERNAME")
        password = get_critical_var(env, "PASSWORD")
        bot_token = get_critical_var(env, "TELEGRAM_BOT_TOKEN")
        chat_id = get_critical_var(env, "TELEGRAM_CHAT_ID")
    except ValueError as e:
        logger.critical(f"Error en variables de entorno: {e}")
        sys.exit(1)

    logger.info("Iniciando el tracker PS3838...")

    # Cargar mapeos y cachés
    sports_mapping = load_sports_mapping()
    game_ids_cache = load_json_file(GAME_IDS_CACHE_FILE) or {}
    last_values_cache = load_json_file(SETTLED_LAST_FILE) or {}

    processed_bets = set()
    consecutive_errors = 0

    while True:
        try:
            bets_data = load_json_file(JSON_INPUT_FILE)
            if not bets_data:
                logger.info("No se encontraron apuestas en bets_today.json.")
            else:
                logger.info(f"Procesando {len(bets_data)} apuesta(s) leída(s).")
                for bet_record in bets_data:
                    bet_info = map_bet_info(bet_record)
                    if bet_info:
                        process_bet(
                            username, password,
                            bot_token, chat_id,
                            bet_info,
                            sports_mapping,
                            game_ids_cache,
                            last_values_cache,
                            processed_bets
                        )
            
            # Guardar cachés
            save_json_file(GAME_IDS_CACHE_FILE, game_ids_cache)
            save_json_file(SETTLED_LAST_FILE, last_values_cache)

            consecutive_errors = 0
        except KeyboardInterrupt:
            logger.info("Programa detenido manualmente por el usuario.")
            save_json_file(GAME_IDS_CACHE_FILE, game_ids_cache)
            save_json_file(SETTLED_LAST_FILE, last_values_cache)
            sys.exit(0)
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error en bucle principal (intento {consecutive_errors}): {e}", exc_info=True)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.critical("Demasiados errores consecutivos. Reiniciando o saliendo...")
                save_json_file(GAME_IDS_CACHE_FILE, game_ids_cache)
                save_json_file(SETTLED_LAST_FILE, last_values_cache)
                time.sleep(5)  # Esperar un poco antes de reiniciar o salir
                sys.exit(1)

        logger.info(f"Esperando {MAIN_LOOP_SLEEP} segundos antes de la siguiente iteración...")
        time.sleep(MAIN_LOOP_SLEEP)


if __name__ == "__main__":
    main()
