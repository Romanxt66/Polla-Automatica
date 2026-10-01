from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from app.jobs import scheduler as sched
from app.models import Competition, Match, MatchStatus
from app.providers.fake import FakeProvider

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


def test_build_registers_three_jobs_without_starting():
    s = sched.build_scheduler()
    assert not s.running
    jobs = {j.id: j for j in s.get_jobs()}
    assert set(jobs) == {sched.SYNC_JOB_ID, sched.SETTLE_JOB_ID, sched.CATCH_UP_JOB_ID}
    settle = jobs[sched.SETTLE_JOB_ID].trigger
    assert isinstance(settle, IntervalTrigger) and settle.interval == timedelta(minutes=5)
    assert all(j.max_instances == 1 and j.coalesce for j in jobs.values())


def test_start_and_stop_are_idempotent():
    sched.start_scheduler()
    first = sched._scheduler
    assert first is not None and first.running
    sched.start_scheduler()  # segunda llamada no crea otro
    assert sched._scheduler is first
    sched.stop_scheduler()
    assert sched._scheduler is None
    sched.stop_scheduler()  # detener dos veces no falla


@pytest.fixture()
def wired(db, monkeypatch):
    """Hace que los wrappers usen la BD de tests y un FakeProvider con hora controlada."""
    monkeypatch.setattr(sched, "SessionLocal", lambda: _Ctx(db))
    provider = FakeProvider(now=lambda: NOW, anchor=NOW.replace(hour=0))
    monkeypatch.setattr(sched, "get_provider", lambda: provider)
    return db


class _Ctx:
    """Sesión compartida que no se cierra al salir del `with` (la cierra el fixture)."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


def test_sync_job_populates_matches(wired):
    sched.run_sync_fixtures()
    assert wired.query(Match).count() == 12


def test_settle_job_closes_finished_matches_in_window(wired, monkeypatch):
    sched.run_sync_fixtures()
    comp = wired.query(Competition).filter_by(code="PL").one()
    # partido que empezó hace 2h30 y el proveedor ya da por terminado
    match = Match(
        external_id="fake-PL-0",
        competition_id=comp.id,
        home_team="x",
        away_team="y",
        kickoff_at=datetime.now(UTC) - timedelta(hours=3),
        status=MatchStatus.SCHEDULED,
    )
    wired.query(Match).filter_by(external_id="fake-PL-0").delete()
    wired.add(match)
    wired.commit()
    # ahora real (datetime.now) para la ventana; el proveedor considera FINISHED (NOW fijo)
    sched.run_settle_matches()
    wired.refresh(match)
    assert match.status == MatchStatus.FINISHED
    assert match.home_score is not None


def test_jobs_swallow_errors(monkeypatch):
    def boom():
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr(sched, "get_provider", boom)
    sched.run_sync_fixtures()  # no debe propagar (no debe matar al scheduler)
    sched.run_settle_matches()


def test_settle_interval_comes_from_settings(monkeypatch):
    monkeypatch.setattr(sched.settings, "settle_interval_minutes", 15)
    job = {j.id: j for j in sched.build_scheduler().get_jobs()}[sched.SETTLE_JOB_ID]
    assert job.trigger.interval == timedelta(minutes=15)
