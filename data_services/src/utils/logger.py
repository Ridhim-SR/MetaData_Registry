import logging
import sys
from datetime import datetime
from pathlib import Path

_FORMAT = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# data_services/logs/ -- gitignored. Set by start_log_file() for a CLI run.
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_file_handler: logging.FileHandler | None = None


def get_logger(name: str) -> logging.Logger:
    """Return a logger with a consistent console format (and the run's log
    file, once start_log_file() has been called).

    Safe to call from any module -- each logger is configured once.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_FORMAT)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    if _file_handler is not None and _file_handler not in logger.handlers:
        logger.addHandler(_file_handler)

    return logger


def start_log_file(command: str) -> Path:
    """Also write every log line of this run to logs/<command>_<time>.log,
    so a run can be looked at (or sent to someone) afterwards."""

    global _file_handler
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{command}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _file_handler = logging.FileHandler(path, encoding="utf-8")
    _file_handler.setFormatter(_FORMAT)
    for name, existing in list(logging.root.manager.loggerDict.items()):
        if isinstance(existing, logging.Logger) and (name.startswith("src.") or name == "__main__"):
            get_logger(name)  # attaches the file handler
    return path
