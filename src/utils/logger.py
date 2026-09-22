"""Structured, secure logging utility with automatic credential sanitization."""

import logging
import re
import os
from pathlib import Path
from typing import Any

# Patterns to sanitize
SENSITIVE_PATTERNS = [
    (re.compile(r'(password|passwd|pwd)\s*[:=]\s*([^\s,;]+)', re.IGNORECASE), r'\1: [REDACTED]'),
    (re.compile(r'(api[-_]?key|secret|token|authorization|auth)\s*[:=]\s*([^\s,;]+)', re.IGNORECASE), r'\1: [REDACTED]'),
    (re.compile(r'(bearer\s+)([a-zA-Z0-9_\-\.]+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(sk-[a-zA-Z0-9]{20,})', re.IGNORECASE), r'[OPENAI_KEY_REDACTED]'),
    (re.compile(r'(cookies?\s*[:=]\s*)([^\n]+)', re.IGNORECASE), r'\1[COOKIES_REDACTED]'),
]


class SanitizingFormatter(logging.Formatter):
    """Custom logging formatter that scrubs sensitive credentials from output."""

    def format(self, record: logging.LogRecord) -> str:
        orig = super().format(record)
        sanitized = orig
        for pattern, replacement in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


def get_logger(name: str = "career_agent") -> logging.Logger:
    """Configures and returns a thread-safe sanitizing logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = SanitizingFormatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    log_dir = Path("logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "career_agent.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass  # Fallback gracefully if directory is read-only

    return logger
