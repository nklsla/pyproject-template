"""Logger factory and structured event helpers.

Project-agnostic: the root logger name is auto-detected from the first
``get_logger`` call, or set explicitly via ``setup_logging``.
"""

import inspect
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Format constants — single source of truth for all levels
# ---------------------------------------------------------------------------

_LOG_FORMAT = "[%(asctime)s][%(levelname)s]-%(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
_RESET = "\x1b[0m"

# ANSI codes for the [LEVEL]-name section, keyed by logging level int
_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG: "\x1b[2;37m",  # dim grey
    logging.INFO: "\x1b[36m",  # cyan
    logging.WARNING: "\x1b[33m",  # yellow
    logging.ERROR: "\x1b[31m",  # red
    logging.CRITICAL: "\x1b[41;1;97m",  # red background + bold white
}

# ANSI codes for the message section, keyed by logging level int
_MSG_COLORS: dict[int, str] = {
    logging.DEBUG: "\x1b[37m",  # white
    logging.INFO: "\x1b[97m",  # bright white
    logging.WARNING: "\x1b[93m",  # bright yellow
    logging.ERROR: "\x1b[91m",  # bright red
    logging.CRITICAL: "\x1b[41;1;97m",  # red background + bold white
}

# ---------------------------------------------------------------------------
# Frame filtering for trace output — only keep application frames
# ---------------------------------------------------------------------------

# Absolute, normcased path of this module file.
_THIS_FILE: str = os.path.normcase(os.path.abspath(__file__))

# Directory containing stdlib logging (e.g. .../lib/python3.13/logging/).
_STDLIB_LOGGING_DIR: str = os.path.normcase(os.path.join(os.path.dirname(logging.__file__), ""))


def _is_internal_frame(filename: str) -> bool:
    """Return True for frames that are NOT application code.

    Excludes: stdlib, this logger module, frozen importlib, site-packages,
    debugpy / pydevd, and runpy.
    """
    if not filename:
        return True
    nc = os.path.normcase(os.path.abspath(filename))
    if nc == _THIS_FILE:
        return True
    if nc.startswith(_STDLIB_LOGGING_DIR):
        return True
    if filename.startswith("<frozen "):
        return True
    return any(frag in nc for frag in ("site-packages", "debugpy", "pydevd", "runpy.py"))


# ---------------------------------------------------------------------------
# Root logger name — auto-detected on first get_logger() call, or set
# explicitly via setup_logging(root=...).
# ---------------------------------------------------------------------------

_ROOT_NAME: str | None = None


# ---------------------------------------------------------------------------
# Formatter — per-section coloring
# ---------------------------------------------------------------------------


class LevelColorFormatter(logging.Formatter):
    """Formats each log line with independent ANSI color per section.

    Sections:
    - ``[timestamp]``  — no color
    - ``[LEVEL]-name`` — colored per ``_LEVEL_COLORS``
    - ``: message``    — colored per ``_MSG_COLORS``
    """

    def __init__(self) -> None:
        super().__init__(datefmt=_DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "context_str"):
            record.context_str = ""

        asctime = self.formatTime(record, self.datefmt)
        level_color = _LEVEL_COLORS.get(record.levelno, "")
        msg_color = _MSG_COLORS.get(record.levelno, "")

        record.message = record.getMessage()

        # Show name.func (omit func for top-level <module> calls)
        source = record.name
        if record.funcName and record.funcName != "<module>":
            source = f"{record.name}.{record.funcName}"

        line = (
            f"[{asctime}]"
            f"{level_color}[{record.levelname}]-{source}{_RESET}"
            f": {msg_color}{record.message}{_RESET}"
        )

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line += "\n" + record.exc_text
        if record.stack_info:
            line += "\n" + self.formatStack(record.stack_info)

        return line


# ---------------------------------------------------------------------------
# Logger subclass — adds optional call-chain tracing at DEBUG level
# ---------------------------------------------------------------------------


class AppLogger(logging.Logger):
    """Logger subclass that optionally emits a DEBUG call-trace record.

    When ``trace=True`` is passed to ``get_logger``, every log call emits
    a second DEBUG record immediately after the original one.  The record
    contains a compact ``file.func -> file.func`` call chain built from
    only the application frames (stdlib, debugpy, logging internals etc.
    are stripped).
    """

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
        self._trace: bool = False

    def handle(self, record: logging.LogRecord) -> None:
        # Emit the original record first.
        super().handle(record)

        # Guard: skip if tracing disabled or if *this* is already a trace
        # record (prevents infinite recursion from the DEBUG emit below).
        if not self._trace or getattr(record, "_is_trace", False):
            return

        # Build user-only call chain.
        raw_frames = traceback.extract_stack()
        user_frames = [f for f in raw_frames if not _is_internal_frame(f.filename)]
        if not user_frames:
            return

        def _label(f: traceback.FrameSummary) -> str:
            file = Path(f.filename).name
            return file if f.name == "<module>" else f"({file}).{f.name}"

        chain = " -> ".join(_label(f) for f in user_frames)

        trace_record = self.makeRecord(
            self.name,
            logging.DEBUG,
            record.pathname,
            record.lineno,
            f"call trace: {chain}",
            args=(),
            exc_info=None,
        )
        trace_record._is_trace = True
        # Use Logger.handle directly to bypass this override.
        logging.Logger.handle(self, trace_record)


# Register AppLogger before any logger is instantiated.
logging.setLoggerClass(AppLogger)


# ---------------------------------------------------------------------------
# Context-injecting filter
# ---------------------------------------------------------------------------


class ContextFilter(logging.Filter):
    """Injects bound key=value context into every log record."""

    def __init__(self, context: dict[str, str] | None = None) -> None:
        super().__init__()
        self._context: dict[str, str] = context or {}

    def filter(self, record: logging.LogRecord) -> bool:
        pairs = "".join(f" {k}={v}" for k, v in self._context.items())
        record.context_str = pairs
        return True

    def bind(self, **kwargs: str) -> None:
        """Add or update context key=value pairs."""
        self._context.update(kwargs)

    def clear(self) -> None:
        """Remove all bound context."""
        self._context.clear()


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

_configured = False
_context_filter = ContextFilter()


def _caller_name() -> str:
    """Derive a logger name from the call site two frames up the stack."""
    frame_info = inspect.stack()[2]
    module: str = frame_info.frame.f_globals.get("__name__") or "<unknown>"
    func: str = frame_info.frame.f_code.co_name
    if func == "<module>":
        return module
    return f"{module}.{func}"


def _ensure_configured(resolved_name: str) -> None:
    """Configure the root logger on first use, auto-detecting root name."""
    global _ROOT_NAME, _configured  # noqa: PLW0603
    if not _configured:
        if _ROOT_NAME is None:
            top = resolved_name.split(".")[0]
            _ROOT_NAME = top if top not in ("__main__", "<unknown>") else "app"
        _setup_root_logger()
        _configured = True


def get_logger(name: str | None = None, *, trace: bool = False) -> AppLogger:
    """Return a configured ``AppLogger`` for the calling site.

    When *name* is omitted the logger name is auto-detected from the caller
    stack frame as ``module.function`` (or just ``module`` when called at
    module level).  Passing *name* explicitly is still supported for full
    backward compatibility.

    Args:
        name: Logger name.  ``None`` means auto-detected from caller.
        trace: When ``True`` every log call emits an additional DEBUG record
            with the compact ``file.func -> file.func`` call chain.

    Returns:
        Configured ``AppLogger``.
    """
    resolved_name = name if name is not None else _caller_name()
    _ensure_configured(resolved_name)

    logger = logging.getLogger(resolved_name)

    if not isinstance(logger, AppLogger):
        # This should never happen since we set AppLogger as the logger class
        # at the module level, but guard will let type checkers know the return type is correct.
        raise TypeError(f"Logger '{resolved_name}' is not an AppLogger subclass")

    # Loggers outside the root hierarchy won't inherit the handler via
    # propagation — attach it directly so formatting is always applied.
    root_name = _ROOT_NAME or "app"
    if not resolved_name.startswith(root_name) and not logger.handlers:
        root = logging.getLogger(root_name)
        for handler in root.handlers:
            logger.addHandler(handler)
        logger.setLevel(root.level)
        logger.propagate = False

    logger._trace = trace
    return logger


def setup_logging(level: str = "INFO", root: str | None = None) -> None:
    """Configure the root logger.

    Call this once at application startup *before* any ``get_logger`` calls
    to set the desired log level and (optionally) the root name.

    Args:
        level: Log level string (e.g. ``"DEBUG"``, ``"INFO"``).
        root: Root logger name.  When omitted the name is auto-detected
            from the first ``get_logger`` call.
    """
    global _ROOT_NAME, _configured
    if root is not None:
        _ROOT_NAME = root
    _setup_root_logger(level)
    _configured = True


def bind_context(**kwargs: str) -> None:
    """Bind key=value pairs to all subsequent log records."""
    _context_filter.bind(**kwargs)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    """Emit a structured log line with explicit key=value fields."""
    parts = [f"event={event}"]
    parts.extend(f"{k}={v}" for k, v in fields.items())
    logger.log(level, " ".join(parts))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _setup_root_logger(level: str = "INFO") -> None:
    """Configure the root application logger."""
    root_name = _ROOT_NAME or "app"
    root = logging.getLogger(root_name)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(LevelColorFormatter())
    handler.addFilter(_context_filter)
    root.addHandler(handler)

    root.propagate = False
