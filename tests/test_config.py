"""tests/test_config.py — validación de config.yaml y validate_config()."""
import pytest

import app.config as config


def _base_cfg():
    return {
        "negocio": {
            "nombre": "Autocares San Sebastián",
            "telefono_contacto": "957 42 90 30",
            "horario_oficina": [
                {
                    "dias": ["lunes", "martes", "miercoles"],
                    "franjas": [["08:00", "15:00"], ["17:00", "19:00"]],
                },
                {"dias": ["jueves", "viernes"], "franjas": [["08:00", "15:00"]]},
            ],
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


def _fails_with(tmp_path, horario, texto):
    import yaml

    cfg = _base_cfg()
    cfg["negocio"]["horario_oficina"] = horario
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"\[CONFIG\] Rule:") as exc:
        config._load_and_validate_yaml(str(path))
    assert texto in str(exc.value)


def test_horario_oficina_overlap_fails(tmp_path):
    _fails_with(
        tmp_path,
        [{"dias": ["lunes"], "franjas": [["09:00", "14:00"], ["13:00", "18:00"]]}],
        "overlapping",
    )


def test_horario_oficina_inverted_range_fails(tmp_path):
    _fails_with(
        tmp_path,
        [{"dias": ["lunes"], "franjas": [["14:00", "09:00"]]}],
        "fin ('09:00') <= inicio ('14:00')",
    )


def test_horario_oficina_repeated_day_across_blocks_fails(tmp_path):
    _fails_with(
        tmp_path,
        [
            {"dias": ["lunes", "martes"], "franjas": [["08:00", "15:00"]]},
            {"dias": ["martes"], "franjas": [["16:00", "19:00"]]},
        ],
        "day 'martes' appears more than once",
    )


def test_horario_oficina_repeated_day_within_block_fails(tmp_path):
    _fails_with(
        tmp_path,
        [{"dias": ["lunes", "lunes"], "franjas": [["08:00", "15:00"]]}],
        "day 'lunes' appears more than once",
    )


def test_horario_oficina_invalid_day_fails(tmp_path):
    _fails_with(
        tmp_path,
        [{"dias": ["miércoles"], "franjas": [["08:00", "15:00"]]}],
        "invalid day 'miércoles'",
    )


def test_horario_oficina_no_blocks_fails(tmp_path):
    _fails_with(tmp_path, [], "non-empty list of blocks")


def test_horario_oficina_flat_old_format_fails(tmp_path):
    _fails_with(tmp_path, [["09:00", "14:00"]], "mapping with exactly")


def test_horario_oficina_block_without_franjas_fails(tmp_path):
    _fails_with(
        tmp_path, [{"dias": ["lunes"], "franjas": []}], "non-empty list of ranges"
    )


def test_horario_oficina_overlap_in_different_blocks_is_allowed(tmp_path):
    import yaml

    cfg = _base_cfg()
    cfg["negocio"]["horario_oficina"] = [
        {"dias": ["lunes"], "franjas": [["08:00", "15:00"]]},
        {"dias": ["martes"], "franjas": [["08:00", "12:00"]]},
    ]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    config._load_and_validate_yaml(str(path))


def test_config_real_horario_oficina_por_dias():
    assert config.NEGOCIO_HORARIO_OFICINA == [
        (
            ("lunes", "martes", "miercoles"),
            (("08:00", "15:00"), ("17:00", "19:00")),
        ),
        (("jueves", "viernes"), (("08:00", "15:00"),)),
    ]


def test_horario_oficina_texto_por_dias(monkeypatch):
    from app.utils import messages

    esperado = (
        "lunes a miércoles laborables de 08:00 a 15:00 y de 17:00 a 19:00; "
        "jueves y viernes laborables de 08:00 a 15:00"
    )
    assert messages._horario_oficina_txt() == esperado
    assert esperado in messages.msg_info()
    assert esperado in messages.tel_y_horario()
    assert esperado in messages.msg_sin_trayecto("A", "B")


def test_horario_oficina_texto_dias_no_consecutivos_y_finde(monkeypatch):
    from app.utils import messages

    monkeypatch.setattr(
        messages,
        "NEGOCIO_HORARIO_OFICINA",
        [
            (("lunes", "miercoles", "viernes"), (("09:00", "13:00"),)),
            (("sabado",), (("10:00", "12:00"),)),
        ],
    )
    assert messages._horario_oficina_txt() == (
        "lunes, miércoles y viernes laborables de 09:00 a 13:00; "
        "sábado de 10:00 a 12:00"
    )


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
