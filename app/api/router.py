from fastapi import APIRouter

from app.api import auth, competitions, groups, matches, predictions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(competitions.router)
api_router.include_router(groups.router)
api_router.include_router(matches.router)
api_router.include_router(predictions.router)
