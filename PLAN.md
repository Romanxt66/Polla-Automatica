# Plan de trabajo: Polla Automática (FastAPI, solo backend)

Dos personas: **Persona A (Núcleo)** y **Persona B (Automatización)**.
Regla de oro: **cada quien es dueño de sus carpetas y no edita las del otro.** Si necesitas un cambio en algo ajeno, pídelo por mensaje/issue.

---

## 0. Reglas de git (leer primero)

- `main` está protegida: **nadie hace push directo**. Todo entra por Pull Request (PR) con aprobación de la otra persona.
- Ramas:
  - `main`: siempre funcional.
  - `feat/base`: fase 0 (la hace Persona A, ver abajo).
  - `feat/a-<tarea>`: ramas de Persona A (ej. `feat/a-auth`).
  - `feat/b-<tarea>`: ramas de Persona B (ej. `feat/b-scoring`).
- Una rama = una tarea pequeña (máx. 1-2 días). PRs chicos = fusiones sin dolor.
- Antes de abrir un PR: `git fetch && git rebase origin/main`, correr `pytest` y `ruff check .`.
- Se fusiona con **squash merge**. Se borra la rama después.
- Commits: `feat: ...`, `fix: ...`, `test: ...`, `chore: ...`.
- **Nunca** subir `.env`, llaves de API ni `__pycache__` (`.gitignore` viene en la fase 0).

---

## 1. Propiedad de carpetas (para no pisarnos)

| Carpeta / archivo | Dueño | Nota |
|---|---|---|
| `app/core/` (config, db, seguridad) | A | B solo lo importa |
| `app/models/` y `alembic/versions/` | A | B pide cambios a A |
| `app/schemas/auth*, group*, prediction*` | A | |
| `app/api/` (routers) | A | |
| `app/services/invites.py`, `predictions.py` | A | |
| `app/providers/` | B | |
| `app/jobs/` | B | |
| `app/services/scoring.py`, `leaderboard.py` | B | |
| `app/schemas/match*, leaderboard*` | B | |
| `tests/` | cada quien en su archivo | `tests/test_<modulo>.py`, nunca editar el del otro |
| `app/main.py`, `pyproject.toml`, `docker-compose.yml` | A | B pide cambios a A (muy pocos) |

**Puntos calientes de conflicto y cómo se evitan:**
- `alembic/versions/`: solo A crea migraciones. La fase 0 crea **todas las tablas en una sola migración**, así no hay cadenas de migraciones en paralelo.
- `app/main.py` y `app/api/router.py`: la fase 0 deja ya incluidos **todos los routers como stubs vacíos**. Nadie vuelve a editarlos, solo llenan su archivo.
- `pyproject.toml`: la fase 0 deja todas las dependencias previstas. Si necesitas una nueva, avisa a A en vez de editar.

---

## 2. Fase 0: base compartida (Persona A, rama `feat/base`)

**Persona B NO empieza a codear hasta que este PR esté fusionado.** Mientras tanto, B puede leer la documentación de la API elegida y preparar los datos de ejemplo del `FakeProvider` (en un archivo local).

Entregables de A:

1. `git init`, `.gitignore`, `README.md`, `.env.example`.
2. `pyproject.toml` con dependencias: fastapi, uvicorn, sqlalchemy 2, alembic, asyncpg/psycopg, pydantic-settings, python-jose, passlib[bcrypt], httpx, apscheduler, pytest, pytest-asyncio, ruff.
3. `docker-compose.yml` (API + Postgres) y `Dockerfile`.
4. `app/core/config.py` (settings desde `.env`), `app/core/db.py` (sesión).
5. **Todos los modelos** en `app/models/`:
   - `User`, `Competition`, `Match`, `Group`, `GroupMember`, `Prediction`, `PointsLedger`, `Invite`.
   - Campos clave de `Match`: `external_id`, `competition_id`, `home_team`, `away_team`, `kickoff_at`, `status` (`SCHEDULED|LIVE|FINISHED|POSTPONED`), `home_score`, `away_score`.
   - `Prediction`: único por `(user_id, match_id, group_id)`.
   - `PointsLedger`: único por `(prediction_id)` → garantiza que los puntos se calculan **una sola vez**.
6. Una migración inicial de Alembic con todo.
7. Interfaz `app/providers/base.py` (contrato, B la implementa):
   ```python
   class ResultsProvider(Protocol):
       async def get_fixtures(self, competition_code: str) -> list[FixtureDTO]: ...
       async def get_match_result(self, external_id: str) -> MatchResultDTO: ...
   ```
   con los DTOs en `app/providers/dto.py`.
8. Routers stub vacíos: `auth`, `groups`, `matches`, `predictions`, y `GET /health`.
9. Fixture de tests con DB de prueba (`tests/conftest.py`).
10. CI simple (opcional): `ruff` + `pytest`.

**Criterio de listo:** `docker compose up` levanta, `/health` responde 200, `alembic upgrade head` crea las tablas y `pytest` pasa.

---

## 3. Persona B: tareas (después de la fase 0)

Cada tarea = una rama = un PR.

### B1. `feat/b-fake-provider`
- `app/providers/fake.py`: implementa `ResultsProvider` con partidos simulados de las 3 competiciones (algunos `SCHEDULED`, algunos `FINISHED` con marcador).
- `tests/test_fake_provider.py`.
- **Hecho cuando:** devuelve fixtures y resultados válidos según los DTOs.

### B2. `feat/b-scoring`
- `app/services/scoring.py`: función **pura** `calculate_points(pred_home, pred_away, real_home, real_away) -> int`.
  - Marcador exacto: 5.
  - Ganador/empate + diferencia de goles correcta: 3.
  - Solo ganador/empate: 1.
  - Otro caso: 0.
- `tests/test_scoring.py` con muchos casos (empates, goleadas, 0-0, etc.).
- **Hecho cuando:** todos los casos pasan. No toca la DB, por eso no choca con nadie.

### B3. `feat/b-sync-fixtures`
- `app/jobs/sync_fixtures.py`: pide fixtures al provider y hace upsert en `Match` (por `external_id`).
- Test usando `FakeProvider`.
- **Hecho cuando:** correrlo dos veces no duplica partidos.

### B4. `feat/b-settle-matches`
- `app/jobs/settle_matches.py`: busca partidos `FINISHED` sin liquidar, calcula puntos de cada `Prediction` con `calculate_points` y escribe `PointsLedger`.
- Debe ser **idempotente** (correrlo 2 veces no duplica puntos).
- Tests.
- **Hecho cuando:** un partido terminado genera los puntos correctos una sola vez.

### B5. `feat/b-leaderboard`
- `app/services/leaderboard.py`: `get_leaderboard(group_id)` → lista ordenada por puntos (desempate: más marcadores exactos, luego orden alfabético).
- Schemas `leaderboard*` en `app/schemas/`.
- Tests.
- **Nota:** el endpoint `GET /groups/{id}/leaderboard` lo conecta A en su router usando esta función (B no edita routers).

### B6. `feat/b-scheduler`
- `app/jobs/scheduler.py`: APScheduler que corre `sync_fixtures` (1 vez al día) y `settle_matches` (cada 5 min, solo si hay partidos en ventana de juego).
- Se engancha al arranque de la app con un hook expuesto por `main.py`. **Pídele a A que lo conecte** (2 líneas).

### B7. `feat/b-api-football` (cuando haya llave)
- `app/providers/api_football.py`: implementa `ResultsProvider`.
- Variable `RESULTS_PROVIDER=fake|api_football` en `.env`.
- Respetar el límite de llamadas: cache y no consultar si no hay partidos en ventana.

---

## 4. Persona A: tareas (después de la fase 0)

### A1. `feat/a-auth`
- `POST /auth/register`, `POST /auth/login` (JWT), `GET /auth/me`.
- Hash de contraseñas con bcrypt, dependencia `get_current_user`.
- Tests.

### A2. `feat/a-groups`
- `POST /groups` (crear, el creador queda como dueño y miembro), `GET /groups` (mis grupos), `GET /groups/{id}` (solo miembros).
- Un grupo se asocia a una competición.
- Tests.

### A3. `feat/a-invites`
- `POST /groups/{id}/invites` (genera código), `POST /groups/join` (unirse con código).
- Reglas: código con expiración opcional, no duplicar miembros.
- Tests.

### A4. `feat/a-matches-endpoints`
- `GET /matches?competition=...&status=...` (lectura de la tabla `Match`).
- Tests con partidos sembrados en la DB de prueba.

### A5. `feat/a-predictions`
- `PUT /groups/{id}/predictions/{match_id}` (crear/editar), `GET /groups/{id}/predictions` (las mías).
- **Reglas:** solo miembros del grupo; **bloqueado si `now >= kickoff_at`**; marcador ≥ 0.
- Tests (incluyendo el bloqueo por hora).

### A6. `feat/a-leaderboard-endpoint`
- `GET /groups/{id}/leaderboard` usando `services/leaderboard.py` de B (se hace cuando B5 esté fusionado).

### A7. `feat/a-wire-scheduler`
- Conectar el scheduler de B (B6) al arranque de la app.

---

## 5. Orden y dependencias

```
Fase 0 (A) ──► fusionada en main
                 │
      ┌──────────┴──────────┐
      A1 → A2 → A3          B1, B2 (en paralelo, sin dependencias)
      A4, A5                B3 → B4 → B5
      │                     B6
      └──► A6 (necesita B5)  └──► A7 (necesita B6)
                            B7 (cuando haya API key)
```

Las integraciones entre personas son solo **A6 y A7**, y ambas consisten en importar una función ya existente. Ahí es donde se sincronizan.

---

## 6. Flujo diario

1. `git checkout main && git pull`
2. `git checkout -b feat/<a|b>-<tarea>`
3. Trabajar, commits pequeños.
4. `git fetch && git rebase origin/main`
5. `pytest` y `ruff check .` en verde.
6. Abrir PR → la otra persona revisa → squash merge → borrar rama.
7. Avisar por mensaje cuando un PR que el otro espera (B5, B6) esté fusionado.

## 7. Reglas de oro

- No editar archivos de la otra persona. Pedirlo.
- No cambiar los modelos sin acordarlo: un cambio de modelo implica migración y afecta a todos.
- No cambiar firmas de funciones compartidas (`calculate_points`, `get_leaderboard`, `ResultsProvider`) sin avisar.
- PRs pequeños y frecuentes; si una rama lleva más de 2 días, dividirla.
- Sin dinero, premios ni apuestas: esto es solo un juego de pronósticos (por Coljuegos).
