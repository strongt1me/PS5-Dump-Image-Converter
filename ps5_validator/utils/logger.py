"""
PS5 Dump Validator – Logger
Einheitliches Logging mit optionalem Datei-Export.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def setup_logger(
    name: str = "ps5_validator",
    verbose: bool = False,
    log_file: str | None = None,
) -> logging.Logger:
    """Logger konfigurieren und zurückgeben."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Konsolen-Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Datei-Handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def get_logger(name: str = "ps5_validator") -> logging.Logger:
    """Vorhandenen Logger abrufen."""
    return logging.getLogger(name)
