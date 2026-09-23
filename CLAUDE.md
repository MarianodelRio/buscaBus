# CLAUDE.md — Buscabus

## Project overview

WhatsApp bot that answers bus schedule queries for an interurban transport company in the province of Córdoba (operator pending confirmation — see D9 in `design.md`). Clients ask for origin, destination and day; the bot replies with that day's direct departures.

- **Framework**: FastAPI + uvicorn
- **External APIs**: WhatsApp Cloud API (Meta) only — no external API per query
- **Background jobs**: APScheduler 3.x — one job, expired-state cleanup
- **Persistence**: none. Bus schedules are parsed once from an Excel file into CSV files in `data/`, loaded into memory at startup, and only read. No database, no writes, no bookings.
- **State**: in-memory conversation state, expires after 30 min of inactivity
- **Deployment**: same GCP VM as Peluquería, its own systemd service and port (see `design.md`, 6.1–6.2)
- **Tests**: pytest — all external APIs mocked, no real credentials needed

**Estado actual: solo diseño, nada implementado.** Todo lo que sigue describe el diseño aprobado en [`design.md`](design.md), que es la única fuente de verdad del proyecto. Este `CLAUDE.md` marca `(pendiente)` cada módulo que aún no existe — no lo trates como código real hasta que el marcado desaparezca.

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
      loader.py                (pendiente) — carga los CSV de data/ a memoria al arrancar, valida integridad
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
  import_excel.py              (pendiente) — el importador (design.md, sección 2.3)
  diff_datos.py                (pendiente) — diff en lenguaje de negocio entre dos versiones de CSV
tests/                         (pendiente) — un fichero por módulo, ver design.md sección 9
watchdog.py                    (pendiente) — copiado de Peluquería, cambia URL y claves de alerta
Makefile                       (pendiente) — fase 5, cambia puerto/dominio/nombre de servicio
```

Ficheros ya creados en esta fase de esqueleto: estructura de carpetas, `config.yaml`, `config_import.yaml`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `pyproject.toml`, `.gitignore`, `README.md`, este `CLAUDE.md`, agentes y comandos de `.claude/`.

---

## Key patterns and invariants

Estos son invariantes del diseño aprobado, no de código existente — guían la implementación de las fases 0-4.

### Límites de WhatsApp
- **Lista interactiva**: máximo **10 filas en total**, sumando todas las secciones. Título de fila: 24 caracteres. Descripción: 72 caracteres.
- **Botones**: máximo **3**, texto de 20 caracteres.
- **Texto**: 4096 caracteres.
- `test_interactive.py` (fase 4) debe comprobar esto en todo constructor dinámico, en especial la lista de destinos, cuya longitud depende del origen elegido.

### Datos
- **Los CSV de `data/` se generan, nunca se editan a mano.** El Excel (`horarios_fuente/HORARIOS NUEVOS.xlsx`) es lo único que edita la empresa. Se versionan en git a propósito (dan diff, historial y vuelta atrás).
- **El importador aborta ante cualquier marca desconocida; no adivina nunca.** Un color sin leyenda, un asterisco sin significado, una parada sin mapear, un tipo de día sin identificar o unas horas que retroceden detienen el import con un mensaje concreto (hoja, celda, motivo).
- Todo el conocimiento que el Excel no dice explícitamente vive en `config_import.yaml`: leyendas de color por hoja, significado de asteriscos por hoja, alias de paradas, agrupación parada→localidad→zona.

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

### Ciclo de actualización de horarios (cuando exista el importador)

```bash
make import   # tools/import_excel.py: Excel → data/*.csv + informe + diff
              # revisar diff e informe de importación
git add data/*.csv
git commit
make update   # despliega en la VM
```

Si algo sale mal tras `make update`, se revierte el commit de los CSV.

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
