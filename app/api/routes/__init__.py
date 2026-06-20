"""API 라우터 묶음."""

from fastapi import APIRouter

from app.api.routes import schedules, sessions, tasks, users

api_router = APIRouter()
api_router.include_router(tasks.router)
api_router.include_router(sessions.router)
api_router.include_router(users.router)
api_router.include_router(schedules.router)
