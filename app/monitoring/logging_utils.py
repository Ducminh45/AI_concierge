import logging
import sys
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime, timezone


class MonsterResortError(Exception):
    """Base exception for Monster Resort"""

    pass


class DatabaseError(MonsterResortError):
    """Database operation failed"""

    pass


class AIServiceError(MonsterResortError):
    """AI service (OpenAI/ChromaDB) failed"""

    pass


class ValidationError(MonsterResortError):
    """Input validation failed"""

    pass


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for production"""

    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        if hasattr(record, "session_id"):
            log_obj["session_id"] = record.session_id
        return json.dumps(log_obj)


def setup_logging(log_level="INFO", log_file="monster_resort.log"):
    """Set up logging with both file and console handlers"""
    logger = logging.getLogger("monster_resort")
    logger.setLevel(log_level)
    logger.handlers.clear()
    # Console handler (human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    # File handler (JSON for parsing)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    # Error file (only errors)
    error_handler = RotatingFileHandler(
        "monster_resort_errors.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    logger.addHandler(error_handler)

    return logger


# Module-level logger instance for import
logger = setup_logging()
