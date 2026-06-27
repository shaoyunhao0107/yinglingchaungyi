"""Re-export every SQLModel table so SQLModel.metadata sees them on import."""
from app.models.user import User, QuotaEvent, ApiKey
from app.models.credential import ProviderCredential
from app.models.job import GenerationJob
from app.models.artifact import Artifact, ArtifactFolder, ArtifactTag
from app.models.folder import Folder
from app.models.tag import Tag
from app.models.template import Template
from app.models.audit import AuditLog
from app.models.chat import ChatConversation, ChatMessage
from app.models.monica_config import MonicaConfig, get_monica_config
from app.models.image_api_config import ImageApiConfig, list_active_image_apis
from app.models.chat_api_config import ChatApiConfig, list_active_chat_apis

__all__ = [
    "User", "QuotaEvent", "ApiKey",
    "ProviderCredential",
    "GenerationJob",
    "Artifact", "ArtifactFolder", "ArtifactTag",
    "Folder", "Tag",
    "Template",
    "AuditLog",
    "ChatConversation", "ChatMessage",
    "MonicaConfig",
    "ImageApiConfig",
    "ChatApiConfig",
]
