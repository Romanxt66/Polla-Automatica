from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession) -> User:
    email = data.email.lower()
    taken = db.scalar(
        select(User).where(
            (func.lower(User.email) == email)
            | (func.lower(User.username) == data.username.lower())
        )
    )
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email o usuario ya registrado")
    user = User(email=email, username=data.username, hashed_password=hash_password(data.password))
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    valid = (
        user is not None
        and user.is_active
        and verify_password(data.password, user.hashed_password)
    )
    if not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> User:
    return current_user
