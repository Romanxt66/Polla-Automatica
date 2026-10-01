import asyncio
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.db import SessionLocal
from app.jobs.settle_matches import DEFAULT_WINDOW, settle_matches
from app.jobs.sync_fixtures import sync_fixtures
from app.providers import get_provider

logger = logging.getLogger(__name__)

SYNC_JOB_ID = "sync_fixtures"
SETTLE_JOB_ID = "settle_matches"
CATCH_UP_JOB_ID = "settle_catch_up"

CATCH_UP_WINDOW = timedelta(days=3)

_scheduler: BackgroundScheduler | None = None


async def _with_provider(job, db):
    """Crea el proveedor, ejecuta el job y cierra el cliente HTTP si lo tiene."""
    provider = get_provider()
    try:
        return await job(db, provider)
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()


def run_sync_fixtures() -> None:
    try:
        with SessionLocal() as db:
            report = asyncio.run(_with_provider(sync_fixtures, db))
        logger.info("sync_fixtures: %s", report)
    except Exception:
        logger.exception("sync_fixtures falló")


def run_settle_matches(window: timedelta = DEFAULT_WINDOW) -> None:
    """Sin partidos dentro de la ventana no hace llamadas a la API (solo liquida en la BD)."""
    try:
        with SessionLocal() as db:
            report = asyncio.run(
                _with_provider(lambda d, p: settle_matches(d, p, window=window), db)
            )
        if report.polled or report.points_created:
            logger.info("settle_matches: %s", report)
    except Exception:
        logger.exception("settle_matches falló")


def run_settle_catch_up() -> None:
    """Repaso diario con ventana amplia por si el servidor estuvo caído durante un partido."""
    run_settle_matches(window=CATCH_UP_WINDOW)


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=UTC)
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}
    scheduler.add_job(
        run_sync_fixtures,
        "cron",
        hour=4,
        minute=0,
        id=SYNC_JOB_ID,
        # además corre una vez poco después de arrancar, para no esperar al día siguiente
        next_run_time=datetime.now(UTC) + timedelta(seconds=10),
        **common,
    )
    scheduler.add_job(
        run_settle_matches,
        "interval",
        minutes=settings.settle_interval_minutes,
        id=SETTLE_JOB_ID,
        **common,
    )
    scheduler.add_job(run_settle_catch_up, "cron", hour=5, minute=0, id=CATCH_UP_JOB_ID, **common)
    return scheduler


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = build_scheduler()
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
