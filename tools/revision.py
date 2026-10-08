"""tools/revision.py — make revision.

Genera `revision/horarios.html` y `revision/horarios.pdf`: la vista de
revisión para negocio (design.md, sección 2.3). Es el único módulo que habla
con git (para encontrar la última versión publicada) y con WeasyPrint (para
el PDF); la comparación en sí vive en `app/services/horarios/diff.py`, que no
toca ni disco ni git.

Nunca se ejecuta sobre `horarios/` inválido, nunca omite el PDF en
silencio si WeasyPrint/Pango no están disponibles, y nunca resuelve una
pregunta pendiente (`Pnn`): solo la muestra junto al dato afectado.
"""

from __future__ import annotations

import argparse
import html
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import date, datetime

from app.services.horarios import diff
from app.services.horarios.loader import (
    calcular_festivos_por_linea,
    calcular_lineas_pueblos,
)
from app.services.horarios.formato import (
    DIAS_INDIVIDUALES,
    Modelo,
    Resultado,
    texto_observacion,
    validar,
)
from app.utils.interactive import descripcion_linea
from app.utils.messages import msg_no_vendible

# Pendientes (`Pnn`) que afectan a una localidad concreta
# de paradas.yaml. Mapeo fijado a mano (design.md, 8, "Correcciones de la
# fase 1", punto 6). Hoy vacío: ninguna localidad tiene un pendiente propio
# fuera de las aldeas con `pendiente:` (sección "Localidades sin hora de
# paso").
PENDIENTES_POR_LOCALIDAD: dict[str, tuple[str, ...]] = {}

REPO_ROOT = Path(__file__).resolve().parent.parent
HORARIOS_DIR = REPO_ROOT / "horarios"
REVISION_DIR = REPO_ROOT / "revision"
ZONA_HORARIA = "Europe/Madrid"

def _ultimo_tag(repo_root: Path) -> str | None:
    """Devuelve el último tag `horarios-*` (orden de versión, más reciente
    primero) o None si no hay ninguno. Lanza RuntimeError si `git` falla."""
    resultado = subprocess.run(
        ["git", "tag", "--list", "horarios-*", "--sort=-version:refname"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"git tag --list falló (código {resultado.returncode}): "
            f"{resultado.stderr.strip()}"
        )
    lineas = [linea for linea in resultado.stdout.splitlines() if linea.strip()]
    return lineas[0] if lineas else None


def _cargar_snapshot(ref: str, repo_root: Path, tmp_dir: Path) -> Path:
    """Extrae `horarios/` tal como estaba en `ref` a `tmp_dir` mediante
    `git archive`. Lanza RuntimeError con un mensaje claro si falla (ref
    inexistente, o `horarios/` no existía en ese ref)."""
    archive = subprocess.run(
        ["git", "archive", ref, "--", "horarios"],
        cwd=repo_root,
        capture_output=True,
    )
    if archive.returncode != 0:
        raise RuntimeError(
            f"no se pudo extraer 'horarios/' de la referencia '{ref}' "
            f"({archive.stderr.decode(errors='replace').strip()})"
        )
    extraer = subprocess.run(
        ["tar", "-x", "-C", str(tmp_dir)],
        input=archive.stdout,
        capture_output=True,
    )
    if extraer.returncode != 0:
        raise RuntimeError(
            f"no se pudo descomprimir el snapshot de '{ref}' "
            f"({extraer.stderr.decode(errors='replace').strip()})"
        )
    snapshot_dir = tmp_dir / "horarios"
    if not snapshot_dir.is_dir():
        raise RuntimeError(
            f"la referencia '{ref}' no contiene un directorio 'horarios/'"
        )
    return snapshot_dir


def resolver_anterior(
    ref: str | None, repo_root: Path
) -> tuple[str | None, Modelo | None]:
    """Resuelve la referencia anterior (autodetectada o dada por
    `--desde`) y devuelve (ref, modelo). (None, None) significa "primera
    versión". Lanza RuntimeError si la referencia no existe o no valida."""
    if ref is None:
        ref = _ultimo_tag(repo_root)
    if ref is None:
        return None, None

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_dir = _cargar_snapshot(ref, repo_root, Path(tmp))
        resultado_anterior = validar(snapshot_dir)
        if resultado_anterior.errores:
            mensajes = "\n".join(f"  - {e}" for e in resultado_anterior.errores)
            raise RuntimeError(
                f"la versión publicada '{ref}' no valida, no se puede "
                f"calcular el diff:\n{mensajes}"
            )
        return ref, resultado_anterior.modelo


def _pendientes_del_modelo(modelo: Modelo) -> set[str]:
    pendientes: set[str] = set(modelo.pendientes)
    if modelo.calendario is not None:
        pendientes.update(modelo.calendario.pendientes)
    for linea in modelo.lineas.values():
        pendientes.update(linea.pendientes)
        for viaje in linea.viajes:
            pendientes.update(viaje.pendientes)
    return pendientes


def _contar_viajes(modelo: Modelo) -> int:
    return sum(len(linea.viajes) for linea in modelo.lineas.values())


def _clases_tabla() -> list[str]:
    # Las 8 clases individuales, en el orden de design.md/formato.py.
    return list(DIAS_INDIVIDUALES)


def _observaciones_usadas_en_tabla(modelo: Modelo, viajes: list, letra: bool) -> list:
    ids: set[str] = set()
    for viaje in viajes:
        if not letra:
            ids.update(viaje.observaciones)
        for paso in viaje.pasos:
            if letra:
                ids.update(paso.observaciones)
    return sorted(ids)


# Por encima de este número de paradas, la tabla se pinta trasponiendo filas
# y columnas (paradas en filas) para que no se salga de la página impresa
# (design.md 8, "Correcciones de la fase 1", punto 2 — Badajoz, 20 paradas).
_MAX_COLUMNAS_TABLA_NORMAL = 12
# Trasponiendo, cada bloque de viajes (ahora columnas) no puede tener más de
# esto, o se sigue saliendo de la página: se reparte en varios bloques.
_MAX_VIAJES_POR_BLOQUE = 8
# Tablas con tantas filas o menos no se parten entre páginas (clase `corta`).
_MAX_FILAS_TABLA_CORTA = 15


def _notas_numeradas(modelo: Modelo, viajes: list) -> dict[str, int]:
    """oid -> n de las observaciones de viaje sin letra, en orden de aparición.
    Los números existen solo en la vista (no hay letras nuevas en el YAML)."""
    notas: dict[str, int] = {}
    for viaje in viajes:
        for oid in viaje.observaciones:
            obs = modelo.observaciones.get(oid)
            if obs is not None and not obs.letra and oid not in notas:
                notas[oid] = len(notas) + 1
    return notas


def _celda_notas(viaje, notas: dict[str, int]) -> str:
    marcas = " ".join(f"[{notas[oid]}]" for oid in viaje.observaciones if oid in notas)
    return f"<td>{marcas}</td>"


def _leyenda_tabla(
    modelo: Modelo, linea, viajes: list, notas: dict[str, int] | None = None
) -> str:
    notas = notas or {}
    leyenda_items = []
    obs_viaje = _observaciones_usadas_en_tabla(modelo, viajes, letra=False)
    obs_paso = _observaciones_usadas_en_tabla(modelo, viajes, letra=True)
    for oid in sorted(set(obs_viaje) | set(obs_paso)):
        obs = modelo.observaciones.get(oid)
        if obs is None:
            continue
        if oid in notas:
            etiqueta = f"[{notas[oid]}] "
        else:
            etiqueta = f"({obs.letra}) " if obs.letra else ""
        texto = f"{html.escape(etiqueta)}{html.escape(texto_observacion(obs, linea))}"
        leyenda_items.append(f"<li>{texto}</li>")
    if not leyenda_items:
        return ""
    return f"<ul class='leyenda'>{''.join(leyenda_items)}</ul>"


def _celda_paso(modelo: Modelo, paso) -> str:
    if paso is None:
        return "<td>—</td>"
    letras = "".join(
        modelo.observaciones[oid].letra or ""
        for oid in paso.observaciones
        if oid in modelo.observaciones
    )
    if paso.llegada != paso.salida:
        hora = f"llega {paso.llegada} · sale {paso.salida}"
    else:
        hora = paso.salida
    return f"<td>{html.escape(hora)}{html.escape(letras)}</td>"


def _render_tabla_normal(
    modelo: Modelo,
    codigos: list[str],
    viajes: list,
    notas: dict[str, int] | None = None,
) -> str:
    notas = notas or {}
    filas_html = []
    cabecera = "".join(
        f"<th>{html.escape(_nombre_parada(modelo, c))}</th>" for c in codigos
    )
    for viaje in viajes:
        horas_por_parada = {p.parada: p for p in viaje.pasos}
        celdas = [
            _celda_paso(modelo, horas_por_parada.get(codigo)) for codigo in codigos
        ]
        pendiente_badge = "".join(
            f'<span class="pendiente">{html.escape(p)}</span>' for p in viaje.pendientes
        )
        celda_notas = _celda_notas(viaje, notas) if notas else ""
        filas_html.append(
            f"<tr>{''.join(celdas)}<td>{pendiente_badge}</td>{celda_notas}</tr>"
        )

    th_notas = "<th>Notas</th>" if notas else ""
    corta = " corta" if len(viajes) <= _MAX_FILAS_TABLA_CORTA else ""
    return (
        f"<table class='horario{corta}'><thead><tr>"
        f"{cabecera}<th>Pendiente</th>{th_notas}</tr></thead><tbody>"
        f"{''.join(filas_html)}</tbody></table>"
    )


def _render_tabla_transpuesta(
    modelo: Modelo,
    codigos: list[str],
    viajes: list,
    notas: dict[str, int] | None = None,
) -> str:
    notas = notas or {}
    bloques = [
        viajes[i : i + _MAX_VIAJES_POR_BLOQUE]
        for i in range(0, len(viajes), _MAX_VIAJES_POR_BLOQUE)
    ]
    partes = []
    for bloque in bloques:
        if not bloque:
            continue
        cabecera = "<th>Parada</th>" + "".join(
            f"<th>{html.escape(v.pasos[0].salida) if v.pasos else ''}</th>"
            for v in bloque
        )
        filas_html = []
        for codigo in codigos:
            celdas = [f"<td>{html.escape(_nombre_parada(modelo, codigo))}</td>"]
            for viaje in bloque:
                paso = next((p for p in viaje.pasos if p.parada == codigo), None)
                celdas.append(_celda_paso(modelo, paso))
            filas_html.append(f"<tr>{''.join(celdas)}</tr>")
        pendientes_fila = "<td>Pendiente</td>" + "".join(
            "<td>"
            + "".join(
                f'<span class="pendiente">{html.escape(p)}</span>' for p in v.pendientes
            )
            + "</td>"
            for v in bloque
        )
        filas_html.append(f"<tr>{pendientes_fila}</tr>")
        if notas:
            notas_fila = "<td>Notas</td>" + "".join(
                _celda_notas(v, notas) for v in bloque
            )
            filas_html.append(f"<tr>{notas_fila}</tr>")
        partes.append(
            "<table class='horario transpuesta corta'><thead><tr>"
            f"{cabecera}</tr></thead><tbody>{''.join(filas_html)}</tbody></table>"
        )
    return "".join(partes)


def _render_tabla_horario(modelo: Modelo, linea, tabla, viajes: list) -> str:
    if not viajes:
        return ""
    codigos = list(tabla.paradas)
    notas = _notas_numeradas(modelo, viajes)
    if len(codigos) > _MAX_COLUMNAS_TABLA_NORMAL:
        cuerpo = _render_tabla_transpuesta(modelo, codigos, viajes, notas)
    else:
        cuerpo = _render_tabla_normal(modelo, codigos, viajes, notas)
    return f"{cuerpo}{_leyenda_tabla(modelo, linea, viajes, notas)}"


def _nombre_parada(modelo: Modelo, codigo: str) -> str:
    parada = modelo.paradas.get(codigo)
    return parada.nombre if parada is not None else codigo


def _indice_buses(modelo: Modelo) -> dict[str, list]:
    """id de `bus:` -> viajes que lo llevan, en el orden de líneas y viajes."""
    indice: dict[str, list] = {}
    for _, linea in sorted(modelo.lineas.items()):
        for viaje in linea.viajes:
            if viaje.bus is not None:
                indice.setdefault(viaje.bus, []).append(viaje)
    return indice


def _render_mismo_autobus(modelo: Modelo, tabla, viajes: list, buses: dict) -> str:
    """Bajo cada tabla: con qué otras tablas comparten autobús sus viajes
    (`bus:<id>`), para que negocio lo compruebe. Nada si ninguno lo declara;
    nunca se cita la propia tabla."""
    entradas: list[str] = []
    for viaje in viajes:
        if viaje.bus is None:
            continue
        for otro in buses.get(viaje.bus, []):
            if otro.tabla == tabla:
                continue
            linea_otra = modelo.lineas.get(otro.linea)
            nombre = linea_otra.nombre if linea_otra is not None else otro.linea
            paradas = otro.tabla.paradas
            sentido = (
                f"de {_nombre_parada(modelo, paradas[0])} "
                f"a {_nombre_parada(modelo, paradas[-1])}"
                if paradas
                else ""
            )
            texto = f"{nombre} ({diff.clase_en_palabras(otro.dias)}, {sentido})"
            if texto not in entradas:
                entradas.append(texto)
    if not entradas:
        return ""
    texto = html.escape("; ".join(entradas))
    return f"<p class='mismo-bus'>mismo autobús que: {texto}</p>"


def _render_estado_dias(linea) -> str:
    clases = _clases_tabla()
    filas = []
    temporadas_orden = [t.nombre for t in linea.temporadas]
    cabecera = "".join(
        f"<th>{html.escape(diff.clase_en_palabras(c))}</th>" for c in clases
    )
    for nombre_temp in temporadas_orden:
        estados = linea.dias.get(nombre_temp, {})
        celdas = []
        for clase in clases:
            estado = estados.get(clase, "sin_datos")
            clase_css = {
                "horario": "horario",
                "sin_servicio": "sin-servicio",
                "sin_datos": "sin-datos",
            }.get(estado, "sin-datos")
            texto_estado = html.escape(diff.estado_en_palabras(estado))
            celdas.append(f"<td class='{clase_css}'>{texto_estado}</td>")
        filas.append(f"<tr><td>{html.escape(nombre_temp)}</td>{''.join(celdas)}</tr>")
    return (
        "<table class='estado-dias'><thead><tr><th>Temporada</th>"
        f"{cabecera}</tr></thead><tbody>{''.join(filas)}</tbody></table>"
    )


def _render_avisos_linea(modelo: Modelo, linea) -> str:
    items = []
    for oid in linea.avisos:
        obs = modelo.observaciones.get(oid)
        if obs is None:
            continue
        items.append(f"<li>{html.escape(texto_observacion(obs, linea))}</li>")
    no_circula_html = ""
    if linea.no_circula:
        meses = ", ".join(html.escape(str(m)) for m in linea.no_circula)
        no_circula_html = f"<p>No circula en: {meses}.</p>"
    if not items and not no_circula_html:
        return ""
    lista = f"<ul>{''.join(items)}</ul>" if items else ""
    return f"<h3>Avisos de la línea</h3>{lista}{no_circula_html}"


def _render_seccion_linea(
    modelo: Modelo, linea, buses: dict[str, list] | None = None
) -> str:
    if buses is None:
        buses = _indice_buses(modelo)
    partes = [f"<h2>{html.escape(linea.nombre)}</h2>"]

    temporadas_txt = "".join(
        f"<li>{html.escape(t.nombre)}: "
        f"{html.escape(diff.rango_en_palabras(t.rango))}</li>"
        for t in linea.temporadas
    )
    partes.append(f"<h3>Temporadas</h3><ul>{temporadas_txt}</ul>")

    partes.append("<h3>Estado de los días</h3>")
    partes.append(_render_estado_dias(linea))

    if linea.pendientes:
        badges = "".join(
            f'<span class="pendiente">{html.escape(p)}</span>' for p in linea.pendientes
        )
        partes.append(f"<p>Pendiente: {badges}</p>")

    partes.append(_render_avisos_linea(modelo, linea))

    partes.append("<h3>Horarios</h3>")

    # Una tabla por `Tabla`, en el orden del fichero (design.md 8,
    # "Correcciones de la fase 1", punto 1): nunca se mezclan ida y vuelta ni
    # se reordenan columnas.
    for tabla in linea.tablas:
        viajes_tabla = [v for v in linea.viajes if v.tabla is tabla]
        if not tabla.paradas:
            continue
        origen = _nombre_parada(modelo, tabla.paradas[0])
        destino = _nombre_parada(modelo, tabla.paradas[-1])
        titulo = (
            f"{html.escape(tabla.temporada)} — "
            f"{html.escape(diff.clase_en_palabras(tabla.dias))} — "
            f"de {html.escape(origen)} a {html.escape(destino)}"
        )
        partes.append(f"<h4>{titulo}</h4>")
        partes.append(_render_tabla_horario(modelo, linea, tabla, viajes_tabla))
        partes.append(_render_mismo_autobus(modelo, tabla, viajes_tabla, buses))

    return "".join(partes)


def _render_seccion_pueblos(modelo: Modelo) -> str:
    """ "Así aparecen las líneas en el bot" (P18): por cada línea, en el orden
    de la lista del bot, su título, la descripción que ve el cliente (misma
    función que `build_lineas`) y sus pueblos con paradas/alias. Después, las
    localidades que ninguna línea usa (solo si hay alguna)."""
    pendientes_modelo = set(modelo.pendientes)
    paradas_por_localidad: dict[str, list] = {}
    for parada in modelo.paradas.values():
        paradas_por_localidad.setdefault(parada.localidad, []).append(parada)

    def _badges(pendientes: tuple[str, ...]) -> str:
        aplicables = [p for p in pendientes if p in pendientes_modelo]
        return "".join(
            f'<span class="pendiente">{html.escape(p)}</span>' for p in aplicables
        )

    def _item(localidad) -> str:
        badges = _badges(PENDIENTES_POR_LOCALIDAD.get(localidad.id, ()))
        alias_txt = (
            f" (alias: {html.escape(', '.join(localidad.alias))})"
            if localidad.alias
            else ""
        )
        nombres = sorted(
            p.nombre for p in paradas_por_localidad.get(localidad.id, [])
        )
        if len(nombres) == 1 and nombres[0] == localidad.nombre:
            detalle = ""
        elif len(nombres) <= 1:
            detalle = f" — para en: {html.escape(nombres[0])}" if nombres else ""
        elif len(nombres) == 2:
            detalle = (
                f" — para en: {html.escape(nombres[0])} o {html.escape(nombres[1])}"
            )
        else:
            primeras = ", ".join(html.escape(n) for n in nombres[:-1])
            detalle = f" — para en: {primeras} o {html.escape(nombres[-1])}"
        return (
            f"<li>{html.escape(localidad.nombre)}{alias_txt}{detalle} {badges}</li>"
        )

    lineas_pueblos = calcular_lineas_pueblos(modelo)
    partes = [
        "<p>Cada pueblo es lo que elige el cliente; si tiene más de una parada, "
        "se indica cuál.</p>"
    ]
    usadas: set[str] = set()
    for lid, ids in lineas_pueblos.items():
        linea = modelo.lineas[lid]
        usadas.update(ids)
        partes.append(f"<h3>{html.escape(linea.titulo)}</h3>")
        partes.append(
            f"<p>En el bot: {html.escape(descripcion_linea(linea, len(ids)))}</p>"
        )
        items = "".join(_item(modelo.localidades[i]) for i in ids)
        partes.append(f"<ul>{items}</ul>")

    sin_linea = sorted(
        (
            loc
            for loc in modelo.localidades.values()
            if loc.id not in usadas and loc.pendiente is None
        ),
        key=lambda loc: loc.nombre,
    )
    if sin_linea:
        partes.append("<h3>Localidades que ninguna línea usa</h3>")
        partes.append(f"<ul>{''.join(_item(loc) for loc in sin_linea)}</ul>")
    return "".join(partes)


def _render_seccion_pendientes(modelo: Modelo) -> str:
    """ "Localidades sin hora de paso" (P15/P32): aldeas en las que algunos
    autobuses paran pero sin hora propia; el bot remite a otra localidad.
    Devuelve "" si no hay ninguna."""
    pendientes = sorted(
        (loc for loc in modelo.localidades.values() if loc.pendiente is not None),
        key=lambda loc: loc.nombre,
    )
    if not pendientes:
        return ""
    partes = ["<h2>Localidades sin hora de paso</h2>"]
    for loc in pendientes:
        badge = html.escape(loc.pendiente or "")
        ver = modelo.localidades.get(loc.ver or "")
        ver_nombre = ver.nombre if ver is not None else (loc.ver or "")
        partes.append(
            f'<h3>{html.escape(loc.nombre)} <span class="pendiente">{badge}</span></h3>'
            f"<p>Consultar en su lugar: {html.escape(ver_nombre)}</p>"
            f"<p>Distancia: a unos {loc.minutos} minutos</p>"
        )
        if loc.aviso is None:
            continue
        filas = []
        for _, linea in sorted(modelo.lineas.items()):
            for viaje in linea.viajes:
                if loc.aviso in viaje.observaciones and viaje.pasos:
                    filas.append(
                        f"<tr><td>{html.escape(linea.nombre)}</td>"
                        f"<td>{html.escape(viaje.temporada)}</td>"
                        f"<td>{html.escape(diff.clase_en_palabras(viaje.dias))}</td>"
                        f"<td>{html.escape(viaje.pasos[0].salida)}</td></tr>"
                    )
        if filas:
            partes.append(
                "<table><tr><th>Línea</th><th>Temporada</th><th>Días</th>"
                f"<th>Primera hora</th></tr>{''.join(filas)}</table>"
            )
        else:
            partes.append("<p>ningún viaje declarado</p>")
    return "".join(partes)


def _fecha_es(fecha: date) -> str:
    return fecha.strftime("%d/%m/%Y")


def _render_seccion_calendario(modelo: Modelo) -> str:
    """ "Calendario": lo que el bot hace con los días especiales, para que
    negocio lo confirme (P03e, P03g, P12b)."""
    calendario = modelo.calendario
    if calendario is None:
        return ""
    partes = ["<h2>Calendario</h2>"]

    partes.append("<h3>Días sin servicio en ninguna línea (todos los años)</h3>")
    if calendario.sin_servicio_todas_las_lineas:
        items = "".join(
            f"<li>{dia:02d}/{mes:02d}</li>"
            for mes, dia in sorted(calendario.sin_servicio_todas_las_lineas)
        )
        partes.append(f"<ul>{items}</ul>")
    else:
        partes.append("<p>Ninguno.</p>")

    partes.append("<h3>Festivos generales</h3>")
    items = "".join(
        f"<li>{_fecha_es(fecha)} — {html.escape(nombre)}</li>"
        for fecha, nombre in sorted(calendario.festivos.items())
    )
    partes.append(f"<ul>{items}</ul>")

    partes.append("<h3>Festivos locales</h3>")
    if calendario.festivos_locales:
        por_linea = calcular_festivos_por_linea(modelo)
        for loc_id in sorted(calendario.festivos_locales):
            localidad = modelo.localidades.get(loc_id)
            nombre_loc = localidad.nombre if localidad is not None else loc_id
            lineas = sorted(
                modelo.lineas[lid].nombre
                for lid, festivos in por_linea.items()
                if any(loc == loc_id for _, loc in festivos.values())
            )
            lineas_txt = html.escape(", ".join(lineas)) if lineas else "ninguna línea"
            items = "".join(
                f"<li>{_fecha_es(fecha)} — {html.escape(nombre)}</li>"
                for fecha, nombre in sorted(calendario.festivos_locales[loc_id].items())
            )
            partes.append(
                f"<p><b>{html.escape(nombre_loc)}</b> — líneas que los aplican: "
                f"{lineas_txt}</p><ul>{items}</ul>"
            )
    else:
        partes.append("<p>Ninguno.</p>")

    partes.append("<h3>Trayectos que no se venden</h3>")
    if modelo.no_vendibles:
        items = []
        for par in sorted(modelo.no_vendibles, key=lambda p: sorted(p)):
            a, b = sorted(par, key=lambda lid: modelo.localidades[lid].nombre)
            nombre_a = modelo.localidades[a].nombre
            nombre_b = modelo.localidades[b].nombre
            items.append(
                f"<li>{html.escape(nombre_a)} ↔ {html.escape(nombre_b)} — el bot "
                f"responde: «{html.escape(msg_no_vendible(nombre_a, nombre_b))}»</li>"
            )
        partes.append(f"<ul>{''.join(items)}</ul>")
    else:
        partes.append("<p>Ninguno.</p>")
    return "".join(partes)


def _render_cambios(cambios: list[str] | None) -> str:
    if cambios is None:
        return "<p>Primera versión.</p>"
    if not cambios:
        return "<p>Sin cambios desde la versión publicada.</p>"
    items = "".join(f"<li>{html.escape(c)}</li>" for c in cambios)
    return f"<ul>{items}</ul>"


_ESTILO = """
@page { size: A4 landscape; margin: 15mm; }
body { font-family: sans-serif; font-size: 10pt; }
table {
  border-collapse: collapse; margin-bottom: 8px; max-width: 100%;
  table-layout: auto;
}
th, td {
  border: 1px solid #999; padding: 3px 6px; text-align: center;
  word-break: break-word;
}
h3, h4 { break-after: avoid; }
table.horario { font-size: 8pt; }
table.horario.corta { break-inside: avoid; }
table.horario.transpuesta { font-size: 8pt; }
table.leyenda, ul.leyenda { list-style: none; padding-left: 0; font-size: 9pt; }
p.mismo-bus { font-size: 9pt; font-style: italic; }
td.sin-servicio { background: #f5c6c6; }
td.sin-datos { background: #f5e6a6; font-style: italic; }
td.horario { background: #d6f0d6; }
span.pendiente {
  background: #ffb347; color: #000; font-weight: bold; padding: 1px 5px;
  border-radius: 3px; margin-right: 3px;
}
"""


def generar_html(
    actual_modelo: Modelo,
    anterior_modelo: Modelo | None,
    cambios: list[str] | None,
    ref: str | None,
    fecha: str,
) -> str:
    """Construye el HTML completo de la revisión. `cambios` es None si es la
    primera versión (nunca se llama a diff.comparar en ese caso)."""
    n_lineas = len(actual_modelo.lineas)
    n_viajes = _contar_viajes(actual_modelo)
    portada = (
        "<h1>Revisión de horarios</h1>"
        f"<p>Fecha: {html.escape(fecha)}</p>"
        f"<p>Versión: {html.escape(ref) if ref else 'sin publicar'}</p>"
        f"<p>Líneas: {n_lineas}</p>"
        f"<p>Viajes: {n_viajes}</p>"
    )

    cambios_html = "<h2>Cambios desde la versión publicada</h2>" + _render_cambios(
        cambios
    )

    buses = _indice_buses(actual_modelo)
    secciones = "".join(
        _render_seccion_linea(actual_modelo, linea, buses)
        for _, linea in sorted(actual_modelo.lineas.items())
    )

    pueblos_html = (
        "<h2>Así aparecen las líneas en el bot</h2>"
        + _render_seccion_pueblos(actual_modelo)
    )

    pendientes_html = _render_seccion_pendientes(actual_modelo)

    calendario_html = _render_seccion_calendario(actual_modelo)

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_ESTILO}</style></head><body>"
        f"{portada}{cambios_html}{secciones}{pueblos_html}{pendientes_html}{calendario_html}"
        "</body></html>"
    )


def _imprimir_errores(resultado: Resultado) -> None:
    print(f"ERRORES ({len(resultado.errores)}):")
    for error in resultado.errores:
        print(f"  ✗ {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera la revisión de horarios/ para negocio"
    )
    parser.add_argument(
        "--desde",
        default=None,
        help="Referencia git a comparar (por defecto, el último tag horarios-*)",
    )
    parser.add_argument(
        "--solo-html", action="store_true", help="No genera el PDF, solo el HTML"
    )
    args = parser.parse_args(argv)

    resultado_actual = validar(HORARIOS_DIR)
    if resultado_actual.errores:
        _imprimir_errores(resultado_actual)
        print("\nhorarios/ no valida: make revision no puede continuar.")
        return 1
    actual_modelo = resultado_actual.modelo
    assert actual_modelo is not None

    try:
        ref, anterior_modelo = resolver_anterior(args.desde, REPO_ROOT)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1

    if anterior_modelo is None:
        cambios: list[str] | None = None
    else:
        cambios = diff.comparar(anterior_modelo, actual_modelo)

    fecha = datetime.now(ZoneInfo(ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")
    html_doc = generar_html(actual_modelo, anterior_modelo, cambios, ref, fecha)

    REVISION_DIR.mkdir(parents=True, exist_ok=True)
    html_path = REVISION_DIR / "horarios.html"
    html_path.write_text(html_doc, encoding="utf-8")
    print(f"Generado: {html_path}")

    if args.solo_html:
        return 0

    try:
        from weasyprint import HTML
    except ImportError:
        print(
            "✗ No se puede generar el PDF: falta el paquete WeasyPrint "
            "(pip install -r requirements-dev.txt). Usa --solo-html si solo "
            "necesitas el HTML."
        )
        return 1

    pdf_path = REVISION_DIR / "horarios.pdf"
    try:
        HTML(string=html_doc).write_pdf(str(pdf_path))
    except OSError as exc:
        print(
            "✗ WeasyPrint está instalado pero no puede renderizar el PDF: "
            f"faltan las librerías del sistema (Pango/cairo). Detalle: {exc}"
        )
        return 1

    print(f"Generado: {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
