# utils/logger.py
import logging

def get_logger(name: str = __name__) -> logging.Logger:
    """Crea y configura un logger con nivel INFO y salida a archivo + consola."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Evitar múltiples handlers si ya existen
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Handler para archivo
        file_handler = logging.FileHandler("ps3838_tracker.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Handler para la consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger
