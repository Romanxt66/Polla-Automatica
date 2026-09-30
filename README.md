# Polla Automática

Backend (FastAPI) de una polla futbolera: grupos privados, pronósticos de marcadores
(Liga BetPlay, Champions, Premier) y ranking calculado automáticamente al terminar cada
partido. **Sin dinero, premios ni apuestas.**

Plan de trabajo y reglas de git: ver [PLAN.md](PLAN.md).

## Desarrollo local

```bash
cp .env.example .env
uv sync
docker compose up -d db          # Postgres
uv run alembic upgrade head      # crear tablas
uv run uvicorn app.main:app --reload
```

Docs interactivas: http://localhost:8000/docs

## Comandos

```bash
uv run pytest          # tests (SQLite en memoria)
uv run ruff check .    # lint
```
