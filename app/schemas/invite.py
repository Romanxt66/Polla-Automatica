from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class InviteCreate(BaseModel):
    # None = no expira
    expires_in_hours: int | None = Field(default=168, ge=1, le=24 * 365)


class InviteOut(BaseModel):
    code: str
    group_id: int
    expires_at: datetime | None


class JoinRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)

    @field_validator("code")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()
