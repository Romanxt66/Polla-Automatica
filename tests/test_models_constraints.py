from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Competition,
    Group,
    GroupMember,
    Invite,
    Match,
    PointsLedger,
    Prediction,
    User,
)


@pytest.fixture()
def base(db):
    user = User(email="a@x.com", username="ana", hashed_password="h")
    comp = db.query(Competition).filter_by(code="PL").one()
    db.add(user)
    db.flush()
    group = Group(name="g", owner_id=user.id, competition_id=comp.id)
    match = Match(
        external_id="m1",
        competition_id=comp.id,
        home_team="A",
        away_team="B",
        kickoff_at=datetime.now(UTC),
    )
    db.add_all([group, match])
    db.commit()
    return {"user": user, "group": group, "match": match}


def add_prediction(db, base):
    p = Prediction(
        user_id=base["user"].id,
        group_id=base["group"].id,
        match_id=base["match"].id,
        home_score=1,
        away_score=0,
    )
    db.add(p)
    db.commit()
    return p


def test_user_email_and_username_unique(db, base):
    db.add(User(email="a@x.com", username="otro", hashed_password="h"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(User(email="b@x.com", username="ana", hashed_password="h"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_group_member_unique(db, base):
    db.add(GroupMember(group_id=base["group"].id, user_id=base["user"].id))
    db.commit()
    db.add(GroupMember(group_id=base["group"].id, user_id=base["user"].id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_prediction_unique_per_user_match_group(db, base):
    add_prediction(db, base)
    with pytest.raises(IntegrityError):
        add_prediction(db, base)


def test_ledger_unique_per_prediction(db, base):
    pred = add_prediction(db, base)

    def entry():
        return PointsLedger(
            prediction_id=pred.id,
            user_id=base["user"].id,
            group_id=base["group"].id,
            match_id=base["match"].id,
            points=3,
        )

    db.add(entry())
    db.commit()
    db.add(entry())
    with pytest.raises(IntegrityError):
        db.commit()


def test_invite_code_unique(db, base):
    def invite():
        return Invite(code="ABCD2345", group_id=base["group"].id, created_by=base["user"].id)

    db.add(invite())
    db.commit()
    db.add(invite())
    with pytest.raises(IntegrityError):
        db.commit()


def test_match_external_id_and_competition_code_unique(db, base):
    comp = db.query(Competition).filter_by(code="PL").one()
    db.add(
        Match(
            external_id="m1",
            competition_id=comp.id,
            home_team="X",
            away_team="Y",
            kickoff_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Competition(code="PL", name="Duplicada"))
    with pytest.raises(IntegrityError):
        db.commit()
