from fastapi import APIRouter

from app.api.routes import (
    activity,
    activity_tracking,
    agent,
    assistant,
    audit,
    auth,
    employees,
    health,
    live,
    notifications,
    organization,
    presence,
    privacy,
    productivity,
    reports,
    screenshots,
    structure,
    telemetry,
    users,
    work,
)
from app.websocket.router import router as websocket_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organization.router)
api_router.include_router(structure.router)
api_router.include_router(employees.router)
api_router.include_router(activity.router)
api_router.include_router(activity_tracking.router)
api_router.include_router(presence.router)
api_router.include_router(agent.router)
api_router.include_router(screenshots.router)
api_router.include_router(live.router)
api_router.include_router(productivity.router)
api_router.include_router(work.router)
api_router.include_router(reports.router)
api_router.include_router(notifications.router)
api_router.include_router(assistant.router)
api_router.include_router(audit.router)
api_router.include_router(privacy.router)
api_router.include_router(telemetry.router)
api_router.include_router(websocket_router)
