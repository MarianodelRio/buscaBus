# services/scheduler.py
"""APScheduler — un único job: limpieza de estados de conversación caducados
(design.md, 5.2)."""
import logging
import time

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import LIMPIAR_ESTADOS_INTERVAL_MIN, TIMEZONE
from app.handlers.conversation import clean_expired_states
from app.utils import metrics

logger = logging.getLogger(__name__)


def job_limpiar_estados_conversacion():
    """Elimina estados de conversación inactivos más de ESTADO_EXPIRACION_MIN
    minutos y purga los limitadores de tasa inactivos."""
    t0 = time.time()
    logger.info("[JOB] START limpiar_estados_conversacion")
    metrics.inc('scheduler_limpiar_runs')
    try:
        clean_expired_states()
    except Exception as e:
        logger.error(f"[JOB] ERROR limpiar_estados_conversacion: {e}", exc_info=True)
    finally:
        logger.info(f"[JOB] END limpiar_estados_conversacion ({time.time() - t0:.1f}s)")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        executors={'default': ThreadPoolExecutor(20)},
        timezone=TIMEZONE,
    )
    scheduler.add_job(
        job_limpiar_estados_conversacion,
        trigger=IntervalTrigger(minutes=LIMPIAR_ESTADOS_INTERVAL_MIN),
        id=job_limpiar_estados_conversacion.__name__,
        name=job_limpiar_estados_conversacion.__name__,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    return scheduler
