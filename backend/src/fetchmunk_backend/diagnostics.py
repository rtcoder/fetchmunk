import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


def redact_diagnostic(message: str) -> str:
    message = re.sub(
        r"(?im)(cookie|authorization|password|token)\s*[:=].*",
        r"\1: [redacted]",
        message,
    )
    return re.sub(r"https?://\S+", "[url]", message)


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_diagnostic(super().format(record))


def configure(data_dir: Path):
    handler = RotatingFileHandler(
        data_dir / "diagnostics.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=4,
        encoding="utf-8",
    )
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("fetchmunk")
    logger.handlers = [handler]
    logger.propagate = False
    return logger
