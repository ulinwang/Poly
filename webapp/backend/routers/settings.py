"""Settings API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from database import get_api_settings, save_api_settings
from models.settings import ApiSettings, ApiSettingsResponse, ProvidersResponse
from providers.factory import list_providers

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/api", response_model=ApiSettingsResponse)
def read_api_settings():
    row = get_api_settings()
    if row is None:
        return {"settings": ApiSettings()}
    return {"settings": ApiSettings(**row)}


@router.put("/api", response_model=ApiSettingsResponse)
def update_api_settings(settings: ApiSettings):
    settings_dict = settings.model_dump(exclude={"id"})
    save_api_settings(settings_dict)
    return {"settings": settings}


@router.get("/general")
def read_general_settings():
    # Placeholder for general settings
    return {"theme": "system", "language": "en"}


@router.put("/general")
def update_general_settings(body: dict):
    # Placeholder for general settings persistence
    return body
