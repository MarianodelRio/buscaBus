"""tests/test_config.py — validación de config.yaml y validate_config()."""
import pytest

import app.config as config


def _base_cfg():
    return {
        "negocio": {
            "nombre": "Autocares San Sebastián",
            "telefono_contacto": "957 42 90 30",
            "horario_oficina": [["09:00", "14:00"], ["17:00", "19:30"]],
            "enlaces": {"compra_online": ""},
        },
        "pueblos_menu_inicio": ["Córdoba", "Pozoblanco"],
    }


def test_valid_config_loads(tmp_path):
    import yaml

    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(_base_cfg()), encoding="utf-8")
    cfg = config._load_and_validate_yaml(str(path))
    assert cfg["negocio"]["nombre"] == "Autocares San Sebastián"


def test_missing_negocio_nombre_fails(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["negocio"]["nombre"] = ""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError):
        config._load_and_validate_yaml(str(path))


def test_horario_oficina_overlap_fails(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["negocio"]["horario_oficina"] = [["09:00", "14:00"], ["13:00", "18:00"]]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError):
        config._load_and_validate_yaml(str(path))


def test_horario_oficina_inverted_range_fails(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["negocio"]["horario_oficina"] = [["14:00", "09:00"]]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError):
        config._load_and_validate_yaml(str(path))


def test_pueblos_menu_inicio_too_many_fails(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["pueblos_menu_inicio"] = [f"Pueblo {i}" for i in range(9)]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError):
        config._load_and_validate_yaml(str(path))


def test_pueblos_menu_inicio_duplicate_fails(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["pueblos_menu_inicio"] = ["Córdoba", "cordoba"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError):
        config._load_and_validate_yaml(str(path))


def test_enlaces_non_string_value_fails(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["negocio"]["enlaces"] = {"compra_online": 123}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError):
        config._load_and_validate_yaml(str(path))


def test_validate_config_fails_without_app_secret(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "1")
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "1")
    monkeypatch.setattr(config, "WHATSAPP_VERIFY_TOKEN", "1")
    monkeypatch.setattr(config, "WHATSAPP_APP_SECRET", "")
    monkeypatch.setattr(config, "ADMIN_PHONE", "34600000000")
    with pytest.raises(RuntimeError, match="WHATSAPP_APP_SECRET"):
        config.validate_config()


def test_validate_config_ok(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "1")
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "1")
    monkeypatch.setattr(config, "WHATSAPP_VERIFY_TOKEN", "1")
    monkeypatch.setattr(config, "WHATSAPP_APP_SECRET", "1")
    monkeypatch.setattr(config, "ADMIN_PHONE", "34600000000")
    config.validate_config()  # no debe lanzar
