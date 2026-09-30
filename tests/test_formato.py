"""tests/test_formato.py — cada regla de design.md 2.3 rechaza su caso con un
mensaje concreto; horarios/ real valida sin errores."""

from __future__ import annotations

from pathlib import Path


from app.services.horarios import formato

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent
HORARIOS_REAL = REPO_ROOT / "horarios"


def _build(
    tmp_path: Path,
    linea_yaml: str,
    paradas_fixture: str = "paradas_base.yaml",
    observaciones_fixture: str = "observaciones_base.yaml",
    linea_nombre: str = "linea-prueba",
    calendario_fixture: str = "calendario_base.yaml",
) -> Path:
    horarios_dir = tmp_path / "horarios"
    (horarios_dir / "lineas").mkdir(parents=True)
    (horarios_dir / "paradas.yaml").write_text(
        (FIXTURES / paradas_fixture).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (horarios_dir / "observaciones.yaml").write_text(
        (FIXTURES / observaciones_fixture).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (horarios_dir / "calendario.yaml").write_text(
        (FIXTURES / calendario_fixture).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (horarios_dir / "lineas" / f"{linea_nombre}.yaml").write_text(
        linea_yaml, encoding="utf-8"
    )
    return horarios_dir


BASE_VALIDA = """\
nombre: Línea de prueba
avisos: []
no_circula: []
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      {fila}
pendientes: []
"""


def test_yaml_mal_formado(tmp_path):
    horarios_dir = tmp_path / "horarios"
    (horarios_dir / "lineas").mkdir(parents=True)
    (horarios_dir / "paradas.yaml").write_text(
        (FIXTURES / "paradas_base.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (horarios_dir / "observaciones.yaml").write_text(
        (FIXTURES / "observaciones_base.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (horarios_dir / "calendario.yaml").write_text(
        (FIXTURES / "calendario_base.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (horarios_dir / "lineas" / "mala.yaml").write_text(
        "nombre: [sin cerrar\n", encoding="utf-8"
    )

    resultado = formato.validar(horarios_dir)
    assert resultado.modelo is None
    assert any("YAML mal formado" in e for e in resultado.errores)


def test_campo_obligatorio_ausente(tmp_path):
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("falta(n) campo(s) obligatorio(s)" in e for e in resultado.errores)


def test_codigo_parada_sin_definir(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00  08:10  -").replace("CCC", "ZZZ")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("código de parada sin definir 'ZZZ'" in e for e in resultado.errores)


def test_letra_de_observacion_sin_definir(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00Q  08:10  08:20")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("letra de observación sin definir 'Q'" in e for e in resultado.errores)


def test_observacion_en_ambito_no_permitido(tmp_path):
    # entra_en_pueblo solo permite ámbito 'parada'; aquí se usa como
    # observación de viaje.
    linea = BASE_VALIDA.format(fila="08:00  08:10  08:20 | entra_en_pueblo")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("ámbito 'viaje' pero no lo permite" in e for e in resultado.errores)


def test_condicion_que_el_motor_no_sabe_aplicar(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00X  08:10  08:20")
    horarios_dir = _build(
        tmp_path,
        linea,
        observaciones_fixture="observaciones_condicion_desconocida.yaml",
    )
    resultado = formato.validar(horarios_dir)
    assert any("condición que el motor no sabe aplicar" in e for e in resultado.errores)


def test_fila_con_numero_de_valores_distinto(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00  08:10")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("2 valores, se esperaban 3" in e for e in resultado.errores)


def test_horas_que_retroceden(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00  07:50  09:00")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("las horas retroceden" in e for e in resultado.errores)


def test_viaje_con_menos_de_2_horas(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00  -  -")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("menos de 2 horas" in e for e in resultado.errores)


def test_temporadas_que_dejan_dias_sin_cubrir(tmp_path):
    linea = """\
nombre: Línea de prueba
temporadas:
  invierno: 01/01 - 30/06
dias:
  invierno:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: invierno
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("día(s) del año sin cubrir" in e for e in resultado.errores)


def test_temporadas_que_se_solapan(tmp_path):
    linea = """\
nombre: Línea de prueba
temporadas:
  invierno: 01/01 - 31/12
  verano: 01/06 - 31/08
dias:
  invierno:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
  verano:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: invierno
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
  - temporada: verano
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("se solapan" in e for e in resultado.errores)


def test_clase_de_dia_sin_declarar(tmp_path):
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    sabado: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("sin declarar" in e for e in resultado.errores)


def test_clase_de_dia_declarada_dos_veces(tmp_path):
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("declaradas dos veces" in e for e in resultado.errores)


def test_horario_sin_tabla(tmp_path):
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    sabado: horario
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("estado 'horario' sin" in e for e in resultado.errores)


def test_a_demanda_sin_telefono_demanda(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00D  08:10  08:20")
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any("no define 'telefono_demanda'" in e for e in resultado.errores)


def test_alias_no_es_lista_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas = """\
zonas:
  zona-test: Zona de prueba
localidades:
  pueblo-a: { nombre: Pueblo A, zona: zona-test, alias: "no-es-lista" }
  pueblo-b: { nombre: Pueblo B, zona: zona-test }
  pueblo-c: { nombre: Pueblo C, zona: zona-test }
paradas:
  AAA: { nombre: Pueblo A, localidad: pueblo-a }
  BBB: { nombre: Pueblo B, localidad: pueblo-b }
  CCC: { nombre: Pueblo C, localidad: pueblo-c }
"""
    (horarios_dir / "paradas.yaml").write_text(paradas, encoding="utf-8")
    resultado = formato.validar(horarios_dir)
    assert any(
        "'alias' debe ser una lista de cadenas" in e for e in resultado.errores
    )


def test_alias_vacio_al_normalizar_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas = """\
zonas:
  zona-test: Zona de prueba
localidades:
  pueblo-a: { nombre: Pueblo A, zona: zona-test, alias: ["La"] }
  pueblo-b: { nombre: Pueblo B, zona: zona-test }
  pueblo-c: { nombre: Pueblo C, zona: zona-test }
paradas:
  AAA: { nombre: Pueblo A, localidad: pueblo-a }
  BBB: { nombre: Pueblo B, localidad: pueblo-b }
  CCC: { nombre: Pueblo C, localidad: pueblo-c }
"""
    (horarios_dir / "paradas.yaml").write_text(paradas, encoding="utf-8")
    resultado = formato.validar(horarios_dir)
    assert any(
        "normaliza a una cadena vacía" in e for e in resultado.errores
    )


def test_alias_duplicado_en_la_misma_localidad_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas = """\
zonas:
  zona-test: Zona de prueba
localidades:
  pueblo-a: { nombre: Pueblo A, zona: zona-test, alias: ["El Ache", "ache"] }
  pueblo-b: { nombre: Pueblo B, zona: zona-test }
  pueblo-c: { nombre: Pueblo C, zona: zona-test }
paradas:
  AAA: { nombre: Pueblo A, localidad: pueblo-a }
  BBB: { nombre: Pueblo B, localidad: pueblo-b }
  CCC: { nombre: Pueblo C, localidad: pueblo-c }
"""
    (horarios_dir / "paradas.yaml").write_text(paradas, encoding="utf-8")
    resultado = formato.validar(horarios_dir)
    assert any("está repetido" in e for e in resultado.errores)


def test_alias_igual_al_propio_nombre_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas = """\
zonas:
  zona-test: Zona de prueba
localidades:
  pueblo-a: { nombre: Pueblo A, zona: zona-test, alias: ["pueblo a"] }
  pueblo-b: { nombre: Pueblo B, zona: zona-test }
  pueblo-c: { nombre: Pueblo C, zona: zona-test }
paradas:
  AAA: { nombre: Pueblo A, localidad: pueblo-a }
  BBB: { nombre: Pueblo B, localidad: pueblo-b }
  CCC: { nombre: Pueblo C, localidad: pueblo-c }
"""
    (horarios_dir / "paradas.yaml").write_text(paradas, encoding="utf-8")
    resultado = formato.validar(horarios_dir)
    assert any(
        "coincide con el propio nombre de la localidad" in e for e in resultado.errores
    )


def test_dos_localidades_mismo_nombre_normalizado_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas = """\
zonas:
  zona-test: Zona de prueba
localidades:
  pueblo-a: { nombre: "Pueblo A", zona: zona-test }
  pueblo-a2: { nombre: "Pueblo, A", zona: zona-test }
  pueblo-c: { nombre: Pueblo C, zona: zona-test }
paradas:
  AAA: { nombre: Pueblo A, localidad: pueblo-a }
  BBB: { nombre: Pueblo B, localidad: pueblo-a2 }
  CCC: { nombre: Pueblo C, localidad: pueblo-c }
"""
    (horarios_dir / "paradas.yaml").write_text(paradas, encoding="utf-8")
    resultado = formato.validar(horarios_dir)
    assert any(
        "tienen el mismo nombre normalizado" in e for e in resultado.errores
    )


def test_parada_coincide_con_nombre_de_otra_localidad_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas = """\
zonas:
  zona-test: Zona de prueba
localidades:
  pueblo-a: { nombre: Pueblo A, zona: zona-test }
  pueblo-b: { nombre: Pueblo B, zona: zona-test }
  pueblo-c: { nombre: Pueblo C, zona: zona-test }
paradas:
  AAA: { nombre: Pueblo A, localidad: pueblo-a }
  BBB: { nombre: "Pueblo B", localidad: pueblo-c }
  CCC: { nombre: Pueblo C, localidad: pueblo-c }
"""
    (horarios_dir / "paradas.yaml").write_text(paradas, encoding="utf-8")
    resultado = formato.validar(horarios_dir)
    assert any(
        "coincide con el nombre de la localidad" in e for e in resultado.errores
    )


def test_horarios_real_avisa_ambiguedad_villafranca():
    resultado = formato.validar(HORARIOS_REAL)
    assert resultado.errores == []
    avisos_villafranca = [a for a in resultado.avisos if "villafranca" in a]
    assert len(avisos_villafranca) == 1
    assert "villafranca-de-cordoba" in avisos_villafranca[0]
    assert "villafranca-de-los-barros" in avisos_villafranca[0]


def test_horarios_real_valida_sin_errores():
    resultado = formato.validar(HORARIOS_REAL)
    assert resultado.errores == []
    assert resultado.modelo is not None


def test_horarios_real_avisa_de_pendientes_y_sin_datos():
    resultado = formato.validar(HORARIOS_REAL)
    assert any("pendiente" in a for a in resultado.avisos)


def test_localidad_sin_usar_avisa(tmp_path):
    # paradas_base.yaml define tres localidades (pueblo-a/b/c); la línea de
    # prueba solo usa las paradas AAA y BBB, así que pueblo-c debe salir en el
    # aviso aunque su parada CCC ya salga en el de paradas sin usar.
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB
      08:00  08:10
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert resultado.errores == []
    assert any(
        "Localidades definidas que ninguna línea usa" in a and "pueblo-c" in a
        for a in resultado.avisos
    )
    assert any(
        "Paradas definidas que ninguna línea usa" in a and "CCC" in a
        for a in resultado.avisos
    )


def test_dos_tablas_con_mismos_extremos_es_error(tmp_path):
    # Dos tablas con la misma temporada, días y extremos de cabecera (aquí,
    # las dos AAA -> CCC) son indistinguibles para el diff y la revisión.
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    CCC
      09:00  09:20
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert any(
        "tablas con temporada 'anual', días 'lunes-viernes', de 'AAA' a 'CCC'" in e
        for e in resultado.errores
    )


def test_paradas_yaml_pendientes_validos(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas_con_pendientes = (
        (FIXTURES / "paradas_base.yaml").read_text(encoding="utf-8")
        + "\npendientes: [P12]\n"
    )
    (horarios_dir / "paradas.yaml").write_text(
        paradas_con_pendientes, encoding="utf-8"
    )
    resultado = formato.validar(horarios_dir)
    assert resultado.errores == []
    assert resultado.modelo is not None
    assert resultado.modelo.pendientes == ("P12",)
    assert any("pendiente P12" in a for a in resultado.avisos)


def test_paradas_yaml_pendiente_malformado_es_error(tmp_path):
    horarios_dir = _build(tmp_path, BASE_VALIDA.format(fila="08:00  08:10  08:20"))
    paradas_con_pendientes = (
        (FIXTURES / "paradas_base.yaml").read_text(encoding="utf-8")
        + "\npendientes: [no-valido]\n"
    )
    (horarios_dir / "paradas.yaml").write_text(
        paradas_con_pendientes, encoding="utf-8"
    )
    resultado = formato.validar(horarios_dir)
    assert any("pendiente inválido 'no-valido'" in e for e in resultado.errores)


def test_observacion_con_marcador_desconocido_es_error(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00  08:10  08:20")
    horarios_dir = _build(
        tmp_path, linea, observaciones_fixture="observaciones_marcador_desconocido.yaml"
    )
    resultado = formato.validar(horarios_dir)
    assert any("marcador desconocido '{otro}'" in e for e in resultado.errores)


def test_observacion_con_marcador_telefono_no_da_error(tmp_path):
    linea = BASE_VALIDA.format(fila="08:00  08:10  08:20")
    horarios_dir = _build(tmp_path, linea)  # observaciones_base.yaml usa {telefono}
    resultado = formato.validar(horarios_dir)
    assert resultado.errores == []


def test_tablas_con_misma_temporada_y_dias_se_distinguen_en_los_avisos(tmp_path):
    # Dos tablas de la misma línea comparten temporada+dias (p.ej. ida y
    # vuelta, ambas anual/sábado): cada una debe llevar una etiqueta distinta
    # ("tabla 1 de 2" / "tabla 2 de 2") para que un aviso o error sepa decir a
    # cuál se refiere.
    linea = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: sin_servicio
    sabado: horario
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: sabado
    tabla: |
      AAA    BBB    CCC
      08:00  08:10  08:20  | P01
  - temporada: anual
    dias: sabado
    tabla: |
      CCC    BBB    AAA
      09:00  09:10  09:20  | P01
"""
    horarios_dir = _build(tmp_path, linea)
    resultado = formato.validar(horarios_dir)
    assert resultado.errores == []
    etiquetas_pendiente = {a for a in resultado.avisos if "fila 1: pendiente P01" in a}
    assert any("tabla 1 de 2" in a for a in etiquetas_pendiente)
    assert any("tabla 2 de 2" in a for a in etiquetas_pendiente)
    # las dos etiquetas deben ser distintas entre sí
    assert len(etiquetas_pendiente) == 2


# ── no_vendibles en paradas.yaml (P12b) ─────────────────────────────────────

_LINEA_A_B = """\
nombre: Línea de prueba
temporadas:
  anual: todo el año
dias:
  anual:
    lunes-viernes: horario
    sabado: sin_servicio
    domingos-festivos: sin_servicio
horarios:
  - temporada: anual
    dias: lunes-viernes
    tabla: |
      AAA    BBB
      08:00  08:10
"""


def _validar_con_no_vendibles(tmp_path: Path, bloque: str):
    horarios_dir = _build(tmp_path, _LINEA_A_B)
    paradas = horarios_dir / "paradas.yaml"
    paradas.write_text(
        paradas.read_text(encoding="utf-8") + "\n" + bloque, encoding="utf-8"
    )
    return formato.validar(horarios_dir)


def test_no_vendibles_valido(tmp_path):
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-b]\n"
    )
    assert resultado.errores == []
    assert resultado.modelo.no_vendibles == frozenset(
        {frozenset({"pueblo-a", "pueblo-b"})}
    )
    assert not any("no_vendibles" in a for a in resultado.avisos)


def test_no_vendibles_localidad_sin_definir_es_error(tmp_path):
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-zzz]\n"
    )
    assert any(
        "paradas.yaml" in e and "no_vendibles" in e and "pueblo-zzz" in e
        for e in resultado.errores
    )


def test_no_vendibles_misma_localidad_dos_veces_es_error(tmp_path):
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-a]\n"
    )
    assert any("la misma localidad dos veces" in e for e in resultado.errores)


def test_no_vendibles_par_repetido_es_error(tmp_path):
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-b]\n  - [pueblo-a, pueblo-b]\n"
    )
    assert any("repetido" in e for e in resultado.errores)


def test_no_vendibles_par_repetido_invertido_es_error(tmp_path):
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-b]\n  - [pueblo-b, pueblo-a]\n"
    )
    assert any("repetido" in e for e in resultado.errores)


def test_no_vendibles_elemento_que_no_es_par_es_error(tmp_path):
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-b, pueblo-c]\n"
    )
    assert any("elemento inválido" in e for e in resultado.errores)


def test_no_vendibles_par_que_ninguna_linea_conecta_avisa(tmp_path):
    # la línea de prueba solo conecta A-B; A-C no lo conecta nadie.
    resultado = _validar_con_no_vendibles(
        tmp_path, "no_vendibles:\n  - [pueblo-a, pueblo-c]\n"
    )
    assert resultado.errores == []
    assert any(
        "no_vendibles" in a and "pueblo-a" in a and "pueblo-c" in a
        and "ninguna línea conecta" in a
        for a in resultado.avisos
    )


def test_horarios_real_declara_los_tres_no_vendibles_de_p12b():
    resultado = formato.validar(HORARIOS_REAL)
    assert resultado.modelo.no_vendibles == frozenset(
        {
            frozenset({"cordoba", "campus-de-rabanales"}),
            frozenset({"cordoba", "alcolea"}),
            frozenset({"campus-de-rabanales", "alcolea"}),
        }
    )
    assert not any("no_vendibles" in a for a in resultado.avisos)
