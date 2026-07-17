"""Logger central de la aplicación.

Proporciona un logger con formato consistente. El nivel depende del entorno
(``DEBUG`` en desarrollo, ``INFO`` en el resto).
"""

import logging
import sys

from app.config.settings import settings


def setup_logger(name: str = "tms_ai_studio") -> logging.Logger:
    """Crea (o reutiliza) el logger de la aplicación."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = logging.DEBUG if settings.APP_ENV == "development" else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = setup_logger()
