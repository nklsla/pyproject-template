"""Tests for logger/ — structured logger factory, context binding, and events."""

import logging

from pytest import CaptureFixture

from logger import (
    AppLogger,
    ContextFilter,
    LevelColorFormatter,
    bind_context,
    get_logger,
    log_event,
    setup_logging,
)


class TestGetLogger:
    def test_returns_logger(self) -> None:
        logger = get_logger("test.module")
        assert isinstance(logger, AppLogger)
        assert logger.name == "test.module"

    def test_logger_inherits_root_config(self) -> None:
        setup_logging("DEBUG", root="market_analysis")
        get_logger("market_analysis.sub")
        root = logging.getLogger("market_analysis")
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 1


class TestLevelColorFormatter:
    def test_format_includes_level_and_logger(self) -> None:
        fmt = LevelColorFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        assert "INFO" in result
        assert "test.logger" in result
        assert "hello" in result

    def test_format_without_context(self) -> None:
        fmt = LevelColorFormatter()
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        assert "msg" in result

    def test_each_level_has_color_codes(self) -> None:
        fmt = LevelColorFormatter()
        for level in (
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ):
            record = logging.LogRecord(
                name="x",
                level=level,
                pathname="",
                lineno=0,
                msg="test",
                args=None,
                exc_info=None,
            )
            result = fmt.format(record)
            assert "[" in result  # ANSI escape present

    def test_timestamp_not_colored(self) -> None:
        fmt = LevelColorFormatter()
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        bracket_pos = result.index("[")
        first_ansi = result.index("[")
        assert bracket_pos < first_ansi


class TestContextFilter:
    def test_bind_injects_context(self) -> None:
        cf = ContextFilter()
        cf.bind(run_id="abc123", stage="news")
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        cf.filter(record)
        assert "run_id=abc123" in record.context_str
        assert "stage=news" in record.context_str

    def test_clear_removes_context(self) -> None:
        cf = ContextFilter()
        cf.bind(run_id="abc")
        cf.clear()
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        cf.filter(record)
        assert record.context_str == ""

    def test_empty_filter_no_context(self) -> None:
        cf = ContextFilter()
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        cf.filter(record)
        assert record.context_str == ""


class TestLogEvent:
    def test_log_event_produces_message(self) -> None:
        setup_logging("DEBUG", root="market_analysis")
        logger = get_logger("market_analysis.test_event")
        log_event(logger, logging.INFO, "test_event", key="value", num=42)


class TestModuleLevelHelpers:
    def test_bind_context(self) -> None:
        bind_context(run_id="xyz")


class TestAutoName:
    def test_auto_name_at_module_level_uses_provided_name(self) -> None:
        logger = get_logger("market_analysis.explicit")
        assert logger.name == "market_analysis.explicit"

    def test_auto_name_inside_function(self) -> None:
        logger = get_logger()
        assert logger.name.endswith(".test_auto_name_inside_function")

    def test_auto_name_returns_app_logger(self) -> None:
        logger = get_logger()
        assert isinstance(logger, AppLogger)

    def test_explicit_name_still_works(self) -> None:
        logger = get_logger("market_analysis.legacy")
        assert logger.name == "market_analysis.legacy"
        assert isinstance(logger, AppLogger)


class TestTraceFlag:
    def test_trace_false_by_default(self) -> None:
        logger = get_logger("market_analysis.notrace")
        assert logger._trace is False

    def test_trace_true_sets_flag(self) -> None:
        logger = get_logger("market_analysis.withtrace", trace=True)
        assert logger._trace is True

    def test_trace_emits_debug_record(self, capsys: CaptureFixture) -> None:
        setup_logging("DEBUG", root="market_analysis")
        logger = get_logger("market_analysis.tracetest", trace=True)
        logger.warning("trigger trace")
        captured = capsys.readouterr().out
        assert "trigger trace" in captured
        assert "call trace:" in captured
        assert " -> " in captured

    def test_trace_on_info_level(self, capsys: CaptureFixture) -> None:
        setup_logging("DEBUG", root="market_analysis")
        logger = get_logger("market_analysis.traceinfo", trace=True)
        logger.info("info trace")
        captured = capsys.readouterr().out
        assert "info trace" in captured
        assert "call trace:" in captured

    def test_trace_on_debug_level(self, capsys: CaptureFixture) -> None:
        setup_logging("DEBUG", root="market_analysis")
        logger = get_logger("market_analysis.tracedebug", trace=True)
        logger.debug("debug trace")
        captured = capsys.readouterr().out
        assert "debug trace" in captured
        assert "call trace:" in captured

    def test_no_trace_no_extra_record(self, capsys: CaptureFixture) -> None:
        setup_logging("DEBUG", root="market_analysis")
        logger = get_logger("market_analysis.notracetest", trace=False)
        logger.warning("no trace here")
        captured = capsys.readouterr().out
        assert "no trace here" in captured
        assert "call trace" not in captured

    def test_trace_excludes_internal_frames(self, capsys: CaptureFixture) -> None:
        setup_logging("DEBUG", root="market_analysis")
        logger = get_logger("market_analysis.filtertest", trace=True)
        logger.info("filter test")
        captured = capsys.readouterr().out
        assert "logging/__init__" not in captured
        assert "logger/__init__" not in captured
