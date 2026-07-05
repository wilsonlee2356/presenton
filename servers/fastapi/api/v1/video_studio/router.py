from fastapi import APIRouter

from api.v1.video_studio.endpoints.video_studio import VIDEO_STUDIO_ROUTER


API_V1_VIDEO_STUDIO_ROUTER = APIRouter(prefix="/api/v1")
API_V1_VIDEO_STUDIO_ROUTER.include_router(VIDEO_STUDIO_ROUTER)
