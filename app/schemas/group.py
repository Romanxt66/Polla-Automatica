from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    competition_code: str = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("competition_code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.strip().upper()


class MemberOut(BaseModel):
    user_id: int
    username: str
    joined_at: datetime


class GroupOut(BaseModel):
    id: int
    name: str
    competition_code: str
    owner_id: int
    member_count: int
    created_at: datetime


class GroupDetail(GroupOut):
    members: list[MemberOut]
