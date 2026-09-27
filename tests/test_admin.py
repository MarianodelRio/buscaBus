"""tests/test_admin.py — informe de estado, ayuda y logs de administración."""
from app.utils.admin import build_help_message, build_status_report, read_log_tail


def test_build_status_report_includes_datos_block():
    report = build_status_report()
    assert "*Datos*" in report
    assert "OK" in report or "ERROR" in report


def test_build_status_report_never_raises(monkeypatch):
    from app.services.horarios import datos as horarios_datos

    monkeypatch.setattr(horarios_datos, "hay_datos", lambda: False)
    report = build_status_report()
    assert "sin datos cargados" in report


def test_build_help_message_mentions_commands():
    help_text = build_help_message()
    for cmd in ("/status", "/help", "/logs", "/restart"):
        assert cmd in help_text


def test_read_log_tail_without_log_file(monkeypatch):
    monkeypatch.setattr("app.utils.admin.LOG_FILE", "")
    assert "no está configurado" in read_log_tail()


def test_read_log_tail_missing_file(monkeypatch):
    monkeypatch.setattr("app.utils.admin.LOG_FILE", "/nonexistent/path.log")
    assert "no encontrado" in read_log_tail()
