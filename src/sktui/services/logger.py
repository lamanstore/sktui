"""Structured rotating file logger for SKTUI."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from sktui.config import DATA


def setup_logger(log_dir: Path | None = None, log_level: int = logging.INFO) -> logging.Logger:
    """Configure rotating file logger at ~/.local/share/sktui/sktui.log."""
    target_dir = log_dir or DATA
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    log_file = target_dir / "sktui.log"
    logger = logging.getLogger("sktui")
    logger.setLevel(log_level)

    # Avoid duplicate handlers on re-entry
    if not logger.handlers:
        try:
            handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB per file
                backupCount=5,              # Keep up to 5 rotated logs
                encoding="utf-8",
            )
            fmt = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s.%(module)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(fmt)
            logger.addHandler(handler)
        except Exception:
            pass

    return logger
