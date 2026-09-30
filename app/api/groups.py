from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models import Competition, Group, GroupMember, Invite
from app.schemas.group import GroupCreate, GroupDetail, GroupOut, MemberOut
from app.schemas.invite import InviteCreate, InviteOut, JoinRequest
from app.schemas.ranking import RankingEntry
from app.services import invites as invites_service
from app.services.group_ranking import get_group_ranking

router = APIRouter(prefix="/groups", tags=["groups"])


def _group_out(group: Group) -> GroupOut:
    return GroupOut(
        id=group.id,
        name=group.name,
        competition_code=group.competition.code,
        owner_id=group.owner_id,
        member_count=len(group.members),
        created_at=group.created_at,
    )


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(data: GroupCreate, db: DbSession, user: CurrentUser) -> GroupOut:
    competition = db.scalar(select(Competition).where(Competition.code == data.competition_code))
    if competition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competición no encontrada")
    group = Group(name=data.name, owner_id=user.id, competition_id=competition.id)
    group.members.append(GroupMember(user_id=user.id))
    db.add(group)
    db.commit()
    return _group_out(group)


@router.get("", response_model=list[GroupOut])
def list_my_groups(db: DbSession, user: CurrentUser) -> list[GroupOut]:
    groups = db.scalars(
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user.id)
        .options(selectinload(Group.members), selectinload(Group.competition))
        .order_by(Group.created_at.desc(), Group.id.desc())
    ).all()
    return [_group_out(g) for g in groups]


@router.post("/join", response_model=GroupOut)
def join_group(data: JoinRequest, db: DbSession, user: CurrentUser) -> GroupOut:
    invite = db.scalar(select(Invite).where(Invite.code == data.code))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Código de invitación no válido")
    if invites_service.is_expired(invite):
        raise HTTPException(status.HTTP_410_GONE, "La invitación expiró")
    group = db.scalar(
        select(Group).where(Group.id == invite.group_id).options(selectinload(Group.members))
    )
    if any(m.user_id == user.id for m in group.members):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya eres miembro de este grupo")
    group.members.append(GroupMember(user_id=user.id))
    try:
        db.commit()
    except IntegrityError:  # doble clic / petición concurrente
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya eres miembro de este grupo") from None
    return _group_out(group)


@router.get("/{group_id}", response_model=GroupDetail)
def get_group(group_id: int, db: DbSession, user: CurrentUser) -> GroupDetail:
    group = db.scalar(
        select(Group)
        .where(Group.id == group_id)
        .options(selectinload(Group.members).selectinload(GroupMember.user))
    )
    # 404 también para no miembros: no revelamos qué grupos existen
    if group is None or all(m.user_id != user.id for m in group.members):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo no encontrado")
    members = [
        MemberOut(user_id=m.user_id, username=m.user.username, joined_at=m.created_at)
        for m in sorted(group.members, key=lambda m: m.id)
    ]
    return GroupDetail(**_group_out(group).model_dump(), members=members)


@router.post("/{group_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    group_id: int, data: InviteCreate, db: DbSession, user: CurrentUser
) -> InviteOut:
    is_member = db.scalar(
        select(GroupMember.id).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user.id
        )
    )
    if is_member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo no encontrado")
    invite = invites_service.create_invite(db, group_id, user.id, data.expires_in_hours)
    return InviteOut(code=invite.code, group_id=group_id, expires_at=invite.expires_at)


@router.get("/{group_id}/leaderboard", response_model=list[RankingEntry])
def get_leaderboard(group_id: int, db: DbSession, user: CurrentUser) -> list[RankingEntry]:
    is_member = db.scalar(
        select(GroupMember.id).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user.id
        )
    )
    if is_member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo no encontrado")
    return get_group_ranking(db, group_id)
