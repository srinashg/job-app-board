"""Mounts every v1 router."""

from fastapi import APIRouter

from app.api.v1 import admin, applications, auth, batches, jobs, privacy, resumes, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(jobs.router)
api_router.include_router(batches.router)
api_router.include_router(applications.router)
api_router.include_router(privacy.router)
api_router.include_router(admin.router)
