import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.main import app
from app.models import Base, Competition


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add_all(
        [
            Competition(code="BETPLAY", name="Liga BetPlay", country="Colombia"),
            Competition(code="UCL", name="UEFA Champions League", country="Europa"),
            Competition(code="PL", name="Premier League", country="Inglaterra"),
        ]
    )
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
