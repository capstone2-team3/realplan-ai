"""v1 라우터 묶음."""

from fastapi import APIRouter

from app.api.v1 import classify, predict, recommend, schedules, session, tasks, update

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(classify.router)
v1_router.include_router(predict.router)
v1_router.include_router(update.router)
v1_router.include_router(recommend.router)
v1_router.include_router(tasks.router)
v1_router.include_router(schedules.router)
v1_router.include_router(session.router)
