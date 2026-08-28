from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from app.config import Config


def _configure_terminal_utf8() -> None:
    """Явно фиксирует UTF-8 для Python terminal streams, если runtime позволяет."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def configure_logging(config: Config) -> None:
    _configure_terminal_utf8()
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = config.logs_dir / "lapbase.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Текущий файл и архивы вместе обеспечивают заданное окно хранения логов.
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
