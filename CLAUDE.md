# CLAUDE.md — Buscabus

## Project overview

WhatsApp bot that answers bus schedule queries for an interurban transport company in the province of Córdoba (operator pending confirmation — see D9 in `design.md`). Clients ask for origin, destination and day; the bot replies with that day's direct departures.

- **Framework**: FastAPI + uvicorn
- **External APIs**: WhatsApp Cloud API (Meta) only — no external API per query
- **Background jobs**: APScheduler 3.x — one job, expired-state cleanup
- **Persistence**: none. Bus schedules live in hand-edited YAML files in `horarios/` (the source of truth, versioned in git), loaded into memory at startup, and only read. No database, no writes, no bookings. The company Excel is used once for the initial migration only.
- **State**: in-memory conversation state, expires after 30 min of inactivity
- **Deployment**: same GCP VM as Peluquería, its own systemd service and port (see `design.md`, 6.1–6.2)
- **Tests**: pytest — all external APIs mocked, no real credentials needed

**Estado actual: fases 1, 2, 3 y 4 implementadas (formato de horarios, validador, herramientas, 15 líneas migradas (fase 1b-1: 12; fase 1b-2 hecha: Peñarroya – Córdoba, Los Blázquez y Hornachuelos – Córdoba, Badajoz recodificada a `VRC` con `bus:`; falta solo el paso manual de borrar `tools/migracion/` cuando negocio apruebe el PDF), motor de consulta, calendario, coincidencia de texto, lectura de fechas y la conversación completa por WhatsApp; ciclo C1 hecho: celda `llegada>salida` (P21), `bus:<id>` para el mismo autobús con validación y aviso heurístico (T-1); ciclo C2 hecho: localidades pendientes (P15/P32) con `pendiente`/`ver`/`minutos`/`aviso?` en `paradas.yaml`, mensaje "Usar X / Otro pueblo" en la conversación y sección "Localidades sin hora de paso" en la revisión; ciclo C3 hecho: pueblos por línea en lugar de zonas (P18): sin `zonas:` en `paradas.yaml`, `Linea.nombre_corto`/`titulo`, `Horarios.lineas_pueblos`, "Ver pueblos por línea" en la conversación y "Así aparecen las líneas en el bot" en la revisión); fase 5 (infraestructura) pendiente.** Todo lo que sigue describe el diseño aprobado en [`design.md`](design.md), que es la única fuente de verdad del proyecto. Este `CLAUDE.md` marca `(pendiente)` cada módulo que aún no existe — no lo trates como código real hasta que el marcado desaparezca.

---

## Module map

```
app/
  config.py                    — constantes + carga y validación de config.yaml
  main.py                      — FastAPI app + lifespan + /health
  handlers/
    webhook.py                 — GET/POST /webhook, copiado de Peluquería salvo el import de conversation y el fallo cerrado sin WHATSAPP_APP_SECRET
    conversation.py            — infraestructura: bloqueo por teléfono, estado con caducidad, comandos de administrador, despacho por estado
    flujo.py                   — la máquina de estados en sí: MENU → SEL_ORIGEN → SEL_DESTINO → SEL_DIA → RESULTADO (design.md, 4.1-4.8)
  services/
    whatsapp.py                — copiado tal cual de Peluquería
    scheduler.py                — 1 job: limpieza de estados cada 10 min
    horarios/
      modelo.py                — entidades inmutables (design.md 2.4); `Paso` con `llegada` y `salida`, `Viaje.bus`
      formato.py               — parser + validador de horarios/ (design.md 2.3); único para tools, tests y loader
      diff.py                  — diferencias entre dos versiones de horarios/ en lenguaje de negocio
      loader.py                — carga horarios/ a memoria al arrancar usando formato.py; índice `lineas_pueblos` (P18)
      query.py                 — motor de consulta (design.md, sección 3)
      calendario.py            — temporada, tipo de día, festivos, periodo escolar
      datos.py                 — contenedor con lock de los datos cargados (Horarios + Matcher + menú de origen), leído por peticiones y por el scheduler
  utils/
    interactive.py             — helpers genéricos copiados de Peluquería + constructores propios de listas/botones (incl. líneas y pueblos por línea)
    messages.py                — todos los textos en español
    matcher.py                 — reglas de coincidencia de texto (design.md, 4.7) y `lineas()` (líneas con sus pueblos)
    fechas.py                  — lector de fechas en formato cerrado día/mes[/año] (design.md, 4.5); sin lenguaje natural
    metrics.py                 — copiado tal cual de Peluquería
    dedup.py                   — copiado tal cual de Peluquería
    rate_limiter.py            — copiado tal cual de Peluquería
    security.py                — copiado tal cual de Peluquería
    admin.py                   — adaptado: quita la salud de Calendar, añade la de datos cargados
tools/
  validar.py                   — make validar
  formatear.py                 — make formatear: realinea tablas sin tocar datos
  revision.py                  — make revision: HTML + PDF para negocio con cambios vs última versión publicada
  telegram_pruebas.py          — make telegram: herramienta interna, la misma conversación por Telegram (long polling) para el feedback de negocio mientras no hay WhatsApp. No se despliega, sin tests propios (design.md 9.1)
  migracion/                   — cuadre_excel.py, de un solo uso: cuadre de horas Excel↔YAML (18 hojas); se borra cuando negocio apruebe el PDF de la fase 1b-2
horarios/                      — FUENTE DE VERDAD: paradas.yaml, observaciones.yaml, lineas/*.yaml (design.md 2.3). Hoy 15 líneas
tests/                         — test_formato, test_formatear, test_diff, test_revision, test_loader, test_query, test_calendario, test_matcher, test_fechas, test_conversation, test_interactive, test_webhook, test_config, test_admin, test_main + fixtures/ (design.md sección 9). `fixtures/horarios_cicloC/`: llegada>salida y `bus:` (ya migrada en C3, sin zonas); `datos_muchas_lineas` en `conftest.py` genera un `horarios/` con 12 líneas para probar la paginación; `fixtures/horarios_pendientes/`: localidades pendientes (C2)
watchdog.py                    (pendiente) — copiado de Peluquería, cambia URL y claves de alerta
Makefile                       — hoy: validar, formatear, revision, telegram. La fase 5 añade publicar, despliegue, puerto/dominio/servicio
```

Ficheros ya creados en esta fase de esqueleto: estructura de carpetas, `config.yaml`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `pyproject.toml`, `.gitignore`, `README.md`, este `CLAUDE.md`, agentes y comandos de `.claude/`. También `docs/preguntas_negocio.txt`: preguntas P01-P27 enviadas a negocio y decisiones D-a a D-p.

---

## Key patterns and invariants

Estos son invariantes del diseño aprobado, no de código existente — guían la implementación de las fases 0-4.

### Límites de WhatsApp
- **Lista interactiva**: máximo **10 filas en total**, sumando todas las secciones. Título de fila: 24 caracteres. Descripción: 72 caracteres.
- **Botones**: máximo **3**, texto de 20 caracteres.
- **Texto**: 4096 caracteres.
- `test_interactive.py` (fase 4) debe comprobar esto en todo constructor dinámico, en especial la lista de destinos, cuya longitud depende del origen elegido.

### Datos
- **`horarios/` es la fuente de verdad y se edita a mano** cuando negocio comunica un cambio. Se versiona en git (diff, historial y vuelta atrás). No hay CSV ni `data/`. El Excel (`horarios_fuente/`) es de un solo uso para la migración inicial.
- **El validador no deja pasar nada ambiguo; nunca adivina.** Parada, letra u observación sin definir, horas que retroceden, clase de día sin declarar o temporadas que no cubren el año detienen `make validar`, el arranque y los tests con un mensaje concreto (fichero, tabla, fila, motivo). Hay un único parser/validador (`formato.py`).
- **Llegada y salida** (P21): una celda `11:55>12:30` (solo en paradas intermedias) es la llegada y la salida de la misma parada. El motor usa la `salida` en el origen y la `llegada` en el destino.
- **Mismo autobús**: se declara con `bus:<id>` tras el `|` y el validador da error si no cuadra; entre pares no declarados solo hay un aviso heurístico (design.md 2.3). "Tramo con tiempo anómalo" se descartó (T-1 cerrado).
- **`sin_servicio` y `sin_datos` son distintos.** El bot nunca presenta un día sin datos como "no hay servicio".
- Las condiciones (`a_demanda`, `solo_viernes_lectivo`, `solo_si_viajeros_desde_cordoba`) tienen ámbito: línea, viaje o **una parada concreta de un viaje**. El texto al cliente de cada observación vive en `horarios/observaciones.yaml`.
- Lo pendiente de negocio se marca con su número (`P01`-`P27`, ver `docs/preguntas_negocio.txt`). Nunca se resuelve una pregunta abierta en silencio.

### Conversación
- **El usuario elige localidad, el resultado muestra la parada.** No se hace elegir entre las paradas físicas de una misma localidad (p.ej. Pozoblanco pueblo/hospital/estación).
- **El bot nunca resuelve un nombre ambiguo en silencio.** Ver la tabla completa de coincidencia en `design.md`, sección 4.7. `Villafranca` (de Córdoba o de los Barros) siempre pregunta, también escrito con errata.
- **Una sola normalización de nombres**, en `formato.py`, compartida por el validador y `matcher.py`.
- **Las fechas escritas usan un formato cerrado** (`día/mes[/año]`, design.md 4.5). No se interpreta lenguaje natural (`mañana`, `el viernes que viene`).
- Los textos no reconocidos se registran con el texto normalizado y el paso, **nunca con el teléfono del cliente**.
- Estados: `MENU → SEL_ORIGEN → SEL_DESTINO → SEL_DIA → RESULTADO`, más `ESCRIBIR_ORIGEN`, `ESCRIBIR_DESTINO`, `ESCRIBIR_FECHA`, `CONFIRMAR_PUEBLO` para las ramas de texto libre.

### Infraestructura
- **Todo en memoria: sin base de datos y sin llamadas externas por consulta.** Los horarios se cargan una vez al arrancar.
- **`zoneinfo`, nunca `pytz`.** Código nuevo, no arrastra la deuda de Peluquería (design.md, 5.6).
- `WHATSAPP_APP_SECRET` es obligatorio desde el primer día — a diferencia de Peluquería, el arranque debe fallar si falta (design.md, 6.4).

---

## Dev commands

```bash
# Instalar dependencias
pip install -r requirements.txt -r requirements-dev.txt

# Arrancar el servidor (desarrollo) — cuando exista app/main.py
uvicorn app.main:app --reload --port 8001

# Tests
pytest

# Coverage
pytest --cov=app --cov-report=term-missing

# Lint
ruff check .
```

### Ciclo de actualización de horarios (desde la fase 1)

```bash
# negocio comunica un cambio → editar horarios/lineas/<linea>.yaml
make formatear   # realinea columnas
make validar     # debe salir sin errores
make revision    # revision/horarios.html + .pdf, con "cambios desde la versión publicada"
                 # enviar el PDF a negocio y esperar confirmación
git add horarios/ && git commit
make publicar    # tag horarios-AAAA-MM-DD + despliegue (fase 5)
```

Si algo sale mal, se vuelve al tag anterior.

---

## Environment variables

Ver [`.env.example`](.env.example) para la plantilla completa. Resumen (design.md, 6.5):

```ini
WHATSAPP_PHONE_NUMBER_ID=   # Obligatoria
WHATSAPP_ACCESS_TOKEN=      # Obligatoria — System User permanente
WHATSAPP_VERIFY_TOKEN=      # Obligatoria
WHATSAPP_APP_SECRET=        # Obligatoria (a diferencia de Peluquería, el arranque falla si falta)
WHATSAPP_API_VERSION=       # Opcional, por defecto v23.0
ADMIN_PHONE=                # Obligatoria — comandos de administrador
PUBLIC_DOMAIN=               # Obligatoria — subdominio sin https://
DUCKDNS_TOKEN=               # Obligatoria
LOG_LEVEL=INFO               # Opcional
LOG_FILE=                    # Opcional
TELEGRAM_BOT_TOKEN=          # Opcional — solo `make telegram` (herramienta interna, design.md 9.1); producción no la usa
```

No hacen falta `GOOGLE_CALENDAR_ID` ni `GOOGLE_CREDENTIALS_PATH`: este bot no usa Google Calendar.

---

## Role System (Strict)

One task = one clean cycle: **plan → implement → review**.

Pass context between roles via explicit artifacts (plan text, file paths, implementation summary). Never skip phases or merge roles.

### Planner
- Produces step-by-step plans, identifies files to modify, defines acceptance criteria.
- Does **NOT** write or modify code.
- Use agent: `planner`

### Coder
- Executes exactly what the plan says, minimal focused changes.
- Does **NOT** redesign, extend scope, or add unrequested features.
- Runs `pytest` before reporting done.
- Use agent: `coder`

### Reviewer
- Evaluates changes against the plan, detects bugs and regressions.
- Does **NOT** implement fixes — reports them for a new cycle.
- Gives the user `pytest` commands to run.
- Use agent: `reviewer`

### Advisor
- Deep technical consultant for architecture and strategy decisions.
- Gives **one clear recommendation** — never "it depends" without resolving it.
- Does **NOT** write code or pseudocode.
- Use agent: `advisor` (Opus model)

### Researcher
- Investigates API capabilities, algorithms, and implementation patterns.
- Reads codebase **first**, then searches externally.
- Does **NOT** invent findings.
- Escalates to `advisor` for multi-approach architectural decisions.
- Use agent: `researcher`

### User-invocable skills
- `/research` — Conversational session to mature an idea into a Research Design Solution (RDS).
- `/new-feature` — Full pipeline: RDS → planner → coder → reviewer, with checkpoint approval at each phase.
