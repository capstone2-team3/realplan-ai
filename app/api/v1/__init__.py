"""v1 라우터 묶음."""

from fastapi import APIRouter

from app.api.v1 import schedules, sessions, tasks, users

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(tasks.router)
v1_router.include_router(sessions.router)
v1_router.include_router(users.router)
v1_router.include_router(schedules.router)
