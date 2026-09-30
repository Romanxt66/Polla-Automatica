# Polla Automática

Backend (FastAPI) de una polla futbolera: grupos privados, pronósticos de marcadores
(Liga BetPlay, Champions, Premier) y ranking calculado automáticamente al terminar cada
partido. **Sin dinero, premios ni apuestas.**

Plan de trabajo y reglas de git: ver [PLAN.md](PLAN.md).

## Desarrollo local

```bash
cp .env.example .env             # y edita las credenciales de tu Postgres
uv sync
uv run alembic upgrade head      # crear tablas
uv run uvicorn app.main:app --reload
```

### Base de datos
La conexión sale **solo de variables de entorno** (o de `.env`, que no se sube a git):

- `DATABASE_URL=postgresql+psycopg://usuario:clave@host:5432/db?sslmode=require`, o bien
- piezas sueltas: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `POSTGRES_DB` y, si tu servidor lo exige, `POSTGRES_SSLMODE=require`. La contraseña puede
  llevar caracteres especiales sin codificar.

Si no hay ninguna de las dos, la app no arranca y dice qué variable falta.

Sin servidor propio, API + Postgres locales en Docker:
`docker compose -f docker-compose.dev.yml up --build`
(con `POSTGRES_HOST=db` en `.env`).

### Despliegue (Coolify)
`docker-compose.yml` no publica puertos en el host: solo `expose: 8000`, y une la API a la red
`coolify` para que alcance a tu Postgres por nombre de host. En Coolify asigna
el dominio al servicio `api` con puerto **8000** y define las variables de entorno
(`DATABASE_URL` o `POSTGRES_*`, `SECRET_KEY`, `CORS_ORIGINS`...). Las variables vacías se ignoran.

Docs interactivas: http://localhost:8000/docs

## Comandos

```bash
uv run pytest          # tests (SQLite en memoria)
uv run ruff check .    # lint
```
