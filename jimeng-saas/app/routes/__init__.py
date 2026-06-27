from app.routes.auth import router as auth_router
from app.routes.jobs import router as jobs_router
from app.routes.artifacts import router as artifacts_router
from app.routes.folders import router as folders_router
from app.routes.tags import router as tags_router
from app.routes.admin import router as admin_router
from app.routes.pages import router as pages_router
from app.routes.templates import router as templates_router
from app.routes.billing import router as billing_router
from app.routes.api_public import router as api_public_router
from app.routes.uploads import router as uploads_router
from app.routes.chat import router as chat_router

__all__ = [
    "auth_router", "jobs_router", "artifacts_router",
    "folders_router", "tags_router",
    "admin_router", "pages_router", "templates_router",
    "billing_router", "api_public_router", "uploads_router", "chat_router",
]
