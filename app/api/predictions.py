from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.models import Group, GroupMember, Match, Prediction
from app.schemas.prediction import PredictionIn, PredictionOut
from app.services.predictions import is_open_for_predictions

router = APIRouter(prefix="/groups/{group_id}/predictions", tags=["predictions"])


def _out(p: Prediction) -> PredictionOut:
    return PredictionOut(
        group_id=p.group_id,
        match_id=p.match_id,
        home_team=p.match.home_team,
        away_team=p.match.away_team,
        kickoff_at=p.match.kickoff_at,
        match_status=p.match.status,
        home_score=p.home_score,
        away_score=p.away_score,
        updated_at=p.updated_at,
    )


def _get_group_for_member(db: DbSession, group_id: int, user_id: int) -> Group:
    group = db.get(Group, group_id)
    is_member = db.scalar(
        select(GroupMember.id).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user_id
        )
    )
    # 404 también para no miembros: no revelamos qué grupos existen
    if group is None or is_member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo no encontrado")
    return group


def _find(db: DbSession, user_id: int, group_id: int, match_id: int) -> Prediction | None:
    return db.scalar(
        select(Prediction)
        .where(
            Prediction.user_id == user_id,
            Prediction.group_id == group_id,
            Prediction.match_id == match_id,
        )
        .options(joinedload(Prediction.match))
    )


@router.put("/{match_id}", response_model=PredictionOut)
def upsert_prediction(
    group_id: int, match_id: int, data: PredictionIn, db: DbSession, user: CurrentUser
) -> PredictionOut:
    group = _get_group_for_member(db, group_id, user.id)
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partido no encontrado")
    if match.competition_id != group.competition_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "El partido no pertenece a la competición del grupo",
        )
    if not is_open_for_predictions(match):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Las predicciones de este partido cerraron")

    prediction = _find(db, user.id, group_id, match_id)
    if prediction is None:
        prediction = Prediction(user_id=user.id, group_id=group_id, match_id=match_id)
        prediction.match = match
        db.add(prediction)
    prediction.home_score = data.home_score
    prediction.away_score = data.away_score
    try:
        db.commit()
    except IntegrityError:  # dos peticiones simultáneas creando la misma predicción
        db.rollback()
        prediction = _find(db, user.id, group_id, match_id)
        if prediction is None:
            raise
        prediction.home_score = data.home_score
        prediction.away_score = data.away_score
        db.commit()
    return _out(prediction)


@router.get("", response_model=list[PredictionOut])
def list_my_predictions(group_id: int, db: DbSession, user: CurrentUser) -> list[PredictionOut]:
    _get_group_for_member(db, group_id, user.id)
    predictions = db.scalars(
        select(Prediction)
        .join(Match, Match.id == Prediction.match_id)
        .where(Prediction.user_id == user.id, Prediction.group_id == group_id)
        .options(joinedload(Prediction.match))
        .order_by(Match.kickoff_at, Match.id)
    )
    return [_out(p) for p in predictions]
