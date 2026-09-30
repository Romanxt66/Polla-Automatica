import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invite

# sin 0/O/1/I para evitar confusiones al dictar el código
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def create_invite(
    db: Session, group_id: int, created_by: int, expires_in_hours: int | None
) -> Invite:
    expires_at = (
        datetime.now(UTC) + timedelta(hours=expires_in_hours) if expires_in_hours else None
    )
    while True:
        code = generate_code()
        if db.scalar(select(Invite.id).where(Invite.code == code)) is None:
            break
    invite = Invite(code=code, group_id=group_id, created_by=created_by, expires_at=expires_at)
    db.add(invite)
    db.commit()
    return invite


def is_expired(invite: Invite) -> bool:
    if invite.expires_at is None:
        return False
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:  # SQLite devuelve fechas sin zona
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)
