from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from app.config import Config


def configure_logging(config: Config) -> None:
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = config.logs_dir / "lapbase.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Current file + archived files approximates the requested 3-day window.
    archive_count = max(1, config.log_retention_days - 1)
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=archive_count,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
