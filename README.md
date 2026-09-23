# Buscabus — Bot de WhatsApp de horarios de autobús

Bot de WhatsApp que informa de los horarios de autobús de una empresa de transporte interurbano de la provincia de Córdoba. El cliente pregunta origen, destino y día; el bot responde con las salidas directas de ese día.

Para quién: personas que necesitan saber a qué hora sale su autobús sin llamar por teléfono ni buscar el PDF de horarios.

---

## Estado del proyecto

**Solo diseño, sin implementar.** Este repositorio contiene por ahora el andamiaje (estructura de carpetas, configuración vacía, documentación) y el Excel de origen. La lógica de aplicación — importador, motor de consulta, conversación — llega en las fases 1 a 4.

**[`design.md`](design.md) es la única fuente de verdad del proyecto.** Ahí está todo: el modelo de datos, el motor de consulta, la conversación completa, qué se reutiliza del bot de la peluquería, la infraestructura, las fases de implementación y las dudas abiertas. Este README no lo duplica.

---

## Arquitectura

FastAPI + WhatsApp Cloud API. Los horarios se importan una vez desde un Excel a CSV versionados en git, y se cargan en memoria al arrancar. Sin base de datos y sin llamada a ninguna API externa por consulta — a diferencia del bot de la peluquería, que consulta Google Calendar en cada mensaje.

---

## Estructura de carpetas

```
buscabus/
  config.yaml            # Negocio: teléfono, horario de oficina, enlaces, pueblos del menú
  config_import.yaml     # Conocimiento del Excel: leyendas de color, alias, zonas
  data/                  # CSV generados por el importador. NO editar a mano
  horarios_fuente/       # El Excel tal cual lo manda la empresa
  app/
    config.py            # Carga y valida config.yaml + variables de entorno
    main.py               # FastAPI app + lifespan + /health
    handlers/             # webhook.py, conversation.py
    services/
      horarios/           # loader.py, query.py, calendario.py — el motor de consulta
      whatsapp.py  scheduler.py
    utils/                # interactive.py, messages.py, matcher.py, fechas.py, ...
  tools/
    import_excel.py       # Excel → CSV, con informe y diff
    diff_datos.py
  tests/
  docs/
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

`requirements-dev.txt` incluye `openpyxl`, que solo hace falta para `tools/import_excel.py` — no se instala en la VM de producción.

---

## El ciclo de actualización de horarios

Cuando la empresa manda un Excel nuevo:

1. Sustituir `horarios_fuente/HORARIOS NUEVOS.xlsx`.
2. `make import` — ejecuta `tools/import_excel.py`, que regenera `data/*.csv` y produce un informe y un diff en lenguaje de negocio.
3. Revisar el diff: qué salidas se han añadido, movido o eliminado, línea por línea.
4. Si todo cuadra, commit de los CSV.
5. `make update` en la VM para desplegar.

Si algo sale mal, se revierte el commit de los CSV — el historial completo de cambios de horario queda en git.

Detalle completo del importador (leyendas de color, cuadre de horas, pruebas doradas) en `design.md`, sección 2.3.

---

## Más información

Todo el detalle de diseño — datos, motor de consulta, conversación completa, infraestructura, fases y dudas abiertas — está en [`design.md`](design.md).
