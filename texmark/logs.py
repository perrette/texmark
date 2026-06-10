import logging

logger = logging.getLogger("texmark")
logger.setLevel(logging.INFO)

# texmark is primarily a CLI: show build progress (INFO and up) on stderr.
# Per-element diagnostics use DEBUG and stay hidden by default. Propagation
# stays on so embedding applications (and pytest's caplog) still receive
# the records through the root logger; the guard avoids stacking handlers
# when the module is re-imported.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
