# Buscabus — Bot de WhatsApp de horarios de autobús

Bot de WhatsApp que informa de los horarios de autobús de una empresa de transporte interurbano de la provincia de Córdoba. El cliente pregunta origen, destino y día; el bot responde con las salidas directas de ese día.

Para quién: personas que necesitan saber a qué hora sale su autobús sin llamar por teléfono ni buscar el PDF de horarios.

---

## Estado del proyecto

**Fase 1 implementada.** Ya existen el formato de horarios (`horarios/`, con 5 líneas de prueba migradas del Excel), el validador y las herramientas `make validar`, `make formatear` y `make revision`. El motor de consulta, la conversación y la infraestructura llegan en las fases 2 a 5. Las 10 líneas restantes se migran en la fase 1b, cuando la empresa responda a `docs/preguntas_negocio.txt`.

**[`design.md`](design.md) es la única fuente de verdad del proyecto.** Ahí está todo: el modelo de datos, el motor de consulta, la conversación completa, qué se reutiliza del bot de la peluquería, la infraestructura, las fases de implementación y las dudas abiertas. Este README no lo duplica.

---

## Arquitectura

FastAPI + WhatsApp Cloud API. Los horarios viven en ficheros YAML editados a mano en `horarios/`, versionados en git, y se cargan en memoria al arrancar. El Excel de la empresa solo se usa una vez, para la migración inicial. Sin base de datos y sin llamada a ninguna API externa por consulta — a diferencia del bot de la peluquería, que consulta Google Calendar en cada mensaje.

---

## Estructura de carpetas

```
buscabus/
  config.yaml            # Negocio: teléfono, horario de oficina, enlaces, pueblos del menú
  horarios/              # FUENTE DE VERDAD de los horarios, editada a mano (design.md 2.3)
  revision/              # HTML + PDF generados para negocio (no se versiona)
  horarios_fuente/       # El Excel inicial, de uso único para la migración
  docs/                  # preguntas_negocio.txt: dudas enviadas a la empresa
  app/
    config.py            # Carga y valida config.yaml + variables de entorno
    main.py               # FastAPI app + lifespan + /health
    handlers/             # webhook.py, conversation.py
    services/
      horarios/           # loader.py, query.py, calendario.py — el motor de consulta
      whatsapp.py  scheduler.py
    utils/                # interactive.py, messages.py, matcher.py, fechas.py, ...
  tools/
    validar.py  formatear.py  revision.py
    migracion/            # Scripts de un solo uso para migrar desde el Excel
  tests/
  .claude/                # Agentes y comandos para trabajar con Claude Code en este repo
```

---

## Cómo arrancar en local

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
# edita .env con tus credenciales de WhatsApp Cloud API

uvicorn app.main:app --reload --port 8001
pytest
```

`requirements-dev.txt` incluye `openpyxl` (solo para la migración inicial desde el Excel) y `weasyprint` (PDF de la vista de revisión). Ninguno se instala en la VM de producción.

---

## El ciclo de actualización de horarios

Cuando la empresa comunica un cambio de horario:

1. Editar la fila correspondiente en `horarios/lineas/<linea>.yaml`.
2. `make formatear` y `make validar` (no debe haber errores).
3. `make revision` — genera `revision/horarios.html` y `.pdf`, con una sección de cambios respecto a la última versión publicada.
4. Enviar el PDF a la empresa y esperar su confirmación.
5. Commit de `horarios/` y `make publicar`.

Si algo sale mal, se vuelve al tag anterior: el historial completo de cambios de horario queda en git.

Detalle completo del formato y las comprobaciones en `design.md`, sección 2.3.

---

## Más información

Todo el detalle de diseño — datos, motor de consulta, conversación completa, infraestructura, fases y dudas abiertas — está en [`design.md`](design.md).
