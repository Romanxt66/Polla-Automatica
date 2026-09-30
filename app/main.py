from fastapi import FastAPI

from app.api.router import api_router

app = FastAPI(title="Polla Automática")
app.include_router(api_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
