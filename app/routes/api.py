"""API routes for system statistics and utilities."""

import os
import logging
from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.telegram_client import get_telegram_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/stats")
async def get_system_stats(current_user: dict = Depends(get_current_user)):
    """Get system statistics for connected users."""
    telegram_manager = get_telegram_manager()
    connected_users = await telegram_manager.get_connected_users()
    total_clients = await telegram_manager.get_client_count()

    return {
        "total_active_clients": total_clients,
        "connected_user_count": len(connected_users),
        "current_user_connected": current_user["id"] in connected_users,
        "connected_users": list(connected_users),  # Only return IDs for privacy
    }


@router.get("/health")
async def debug_telegram_config():
    """Debug endpoint to check Telegram API configuration."""
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    return {
        "telegram_api_id_exists": bool(api_id),
        "telegram_api_id_value": api_id[:8] + "..." if api_id else None,
        "telegram_api_hash_exists": bool(api_hash),
        "telegram_api_hash_value": api_hash[:8] + "..." if api_hash else None,
    }


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}
