import importlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.router import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Arranca/detiene el scheduler de B (app/jobs/scheduler.py) si SCHEDULER_ENABLED=true.

    Contrato con el módulo de B: `start_scheduler()` y `stop_scheduler()`, ambas sin
    argumentos y síncronas. Se importa de forma perezosa para que la app arranque aunque
    ese módulo todavía no exista.
    """
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = importlib.import_module("app.jobs.scheduler")
        scheduler.start_scheduler()
        logger.info("Scheduler iniciado")
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop_scheduler()
            logger.info("Scheduler detenido")


app = FastAPI(title="Polla Automática", lifespan=lifespan)
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(api_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
