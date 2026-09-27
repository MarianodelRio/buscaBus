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

**Estado actual: fase 1 implementada (formato de horarios, validador, herramientas y 5 líneas de prueba); fases 2-5 pendientes.** Todo lo que sigue describe el diseño aprobado en [`design.md`](design.md), que es la única fuente de verdad del proyecto. Este `CLAUDE.md` marca `(pendiente)` cada módulo que aún no existe — no lo trates como código real hasta que el marcado desaparezca.

---

## Module map

```
app/
  config.py                    (pendiente) — constantes + carga y validación de config.yaml
  main.py                      (pendiente) — FastAPI app + lifespan + /health
  handlers/
    webhook.py                 (pendiente) — GET/POST /webhook, copiado de Peluquería salvo el import de conversation
    conversation.py            (pendiente) — máquina de estados: MENU → SEL_ORIGEN → SEL_DESTINO → SEL_DIA → RESULTADO
  services/
    whatsapp.py                (pendiente) — copiado tal cual de Peluquería
    scheduler.py                (pendiente) — 1 job: limpieza de estados cada 10 min
    horarios/
      modelo.py                — entidades inmutables (design.md 2.4)
      formato.py               — parser + validador de horarios/ (design.md 2.3); único para tools, tests y loader
      diff.py                  — diferencias entre dos versiones de horarios/ en lenguaje de negocio
      loader.py                (pendiente) — carga horarios/ a memoria al arrancar usando formato.py
      query.py                 (pendiente) — motor de consulta (design.md, sección 3)
      calendario.py            (pendiente) — temporada, tipo de día, festivos, periodo escolar
  utils/
    interactive.py             (pendiente) — helpers genéricos copiados de Peluquería + constructores propios
    messages.py                (pendiente) — todos los textos en español
    matcher.py                 (pendiente) — reglas de coincidencia de texto (design.md, 4.7)
    fechas.py                  (pendiente) — parseo de "25/12", "el viernes que viene", "mañana"
    metrics.py                 (pendiente) — copiado tal cual de Peluquería
    dedup.py                   (pendiente) — copiado tal cual de Peluquería
    rate_limiter.py            (pendiente) — copiado tal cual de Peluquería
    security.py                (pendiente) — copiado tal cual de Peluquería
    admin.py                   (pendiente) — adaptado: quita la salud de Calendar, añade la de datos cargados
tools/
  validar.py                   — make validar
  formatear.py                 — make formatear: realinea tablas sin tocar datos
  revision.py                  — make revision: HTML + PDF para negocio con cambios vs última versión publicada
  migracion/                   — cuadre_excel.py, de un solo uso: cuadre de horas Excel↔YAML; se borra en la fase 1b
horarios/                      — FUENTE DE VERDAD: paradas.yaml, observaciones.yaml, lineas/*.yaml (design.md 2.3). Hoy 5 líneas de prueba; las 10 restantes en la fase 1b
tests/                         — test_formato, test_formatear, test_diff, test_revision + fixtures/; el resto llega con cada fase (design.md sección 9)
watchdog.py                    (pendiente) — copiado de Peluquería, cambia URL y claves de alerta
Makefile                       — hoy: validar, formatear, revision. La fase 5 añade publicar, despliegue, puerto/dominio/servicio
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
- **`sin_servicio` y `sin_datos` son distintos.** El bot nunca presenta un día sin datos como "no hay servicio".
- Las condiciones (`a_demanda`, `solo_viernes_lectivo`, `solo_si_viajeros_desde_cordoba`) tienen ámbito: línea, viaje o **una parada concreta de un viaje**. El texto al cliente de cada observación vive en `horarios/observaciones.yaml`.
- Lo pendiente de negocio se marca con su número (`P01`-`P27`, ver `docs/preguntas_negocio.txt`). Nunca se resuelve una pregunta abierta en silencio.

### Conversación
- **El usuario elige localidad, el resultado muestra la parada.** No se hace elegir entre las paradas físicas de una misma localidad (p.ej. Pozoblanco pueblo/hospital/estación).
- **El bot nunca resuelve un nombre ambiguo en silencio.** Ver la tabla completa de coincidencia en `design.md`, sección 4.7. `Villafranca` (de Córdoba o de los Barros) siempre pregunta.
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
