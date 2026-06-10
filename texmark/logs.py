import logging

logger = logging.getLogger("texmark")
logger.setLevel(logging.INFO)


def setup_console_logging():
    """Attach a plain stderr handler for CLI use.

    Called from the console entry points (texmark, texmark-journal), not at
    import time: a library import must not add handlers, or an embedding
    application with its own root handler would see every record twice.
    Per-element diagnostics use DEBUG and stay hidden by default.
    """
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
