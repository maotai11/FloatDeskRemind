"""
Rotating file logger for FloatDesk Remind.
5MB per file, 3 backups.
Falls back to NullHandler if log dir is not writable (e.g. corporate locked machine).
"""
import logging
from logging.handlers import RotatingFileHandler


def setup_logger(name: str = 'floatdesk') -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler — may fail on read-only or locked machines; degrade gracefully
    try:
        from src.core.paths import LOG_DIR, ensure_dirs
        ensure_dirs()
        log_file = LOG_DIR / 'floatdesk.log'
        fh = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        # Don't crash the app if the log file can't be created
        logger.addHandler(logging.NullHandler())
        # stderr is available in dev mode even without a file handler
        import sys
        print(f'[floatdesk] WARNING: could not set up file logger: {e}', file=sys.stderr)

    # Console handler (useful in dev; no-op in windowed EXE since there's no console)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


logger = setup_logger()
