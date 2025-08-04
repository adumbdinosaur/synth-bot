"""Public dashboard routes."""

import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.database import get_database_manager
from app.auth import get_current_user_with_session_check
from app.telegram_client import get_telegram_manager

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/public")


@router.get("", response_class=HTMLResponse)
async def public_dashboard(
    request: Request, current_user: dict = Depends(get_current_user_with_session_check)
):
    """Public dashboard showing users who have enabled public control."""
    try:
        db_manager = get_database_manager()
        public_users = await db_manager.get_public_users()

        return templates.TemplateResponse(
            "public_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "users": public_users,
                "total_users": len(public_users),
            },
        )
    except Exception as e:
        logger.error(f"Error loading public dashboard: {e}")
        return templates.TemplateResponse(
            "public_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "users": [],
                "error": "Failed to load public dashboard",
            },
        )


@router.get("/sessions", response_class=HTMLResponse)
async def public_sessions_dashboard(
    request: Request, current_user: dict = Depends(get_current_user_with_session_check)
):
    """Public dashboard showing all active Telegram sessions."""
    try:
        db_manager = get_database_manager()

        # Get all active sessions from database
        active_sessions = await db_manager.get_all_active_sessions()

        # Get connection status from telegram manager
        telegram_manager = get_telegram_manager()
        connected_users_info = await telegram_manager.get_connected_users()
        connected_user_ids = {user["user_id"] for user in connected_users_info}

        # Enhance session data with real-time connection status and Telegram names
        connected_users_by_id = {user["user_id"]: user for user in connected_users_info}
        for session in active_sessions:
            session["is_connected"] = session["user_id"] in connected_user_ids
            # If user is connected, try to get their Telegram display name
            if session["is_connected"] and session["user_id"] in connected_users_by_id:
                telegram_user = connected_users_by_id[session["user_id"]]
                # Use Telegram username if available, otherwise fall back to database username
                if telegram_user.get("username"):
                    session["display_name"] = f"@{telegram_user['username']}"
                else:
                    session["display_name"] = (
                        session["username"] or f"User {session['user_id']}"
                    )
            else:
                session["display_name"] = (
                    session["username"] or f"User {session['user_id']}"
                )

        return templates.TemplateResponse(
            "public_sessions_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "sessions": active_sessions,
                "total_sessions": len(active_sessions),
                "connected_sessions": len(
                    [s for s in active_sessions if s["is_connected"]]
                ),
            },
        )
    except Exception as e:
        logger.error(f"Error loading public sessions dashboard: {e}")
        return templates.TemplateResponse(
            "public_sessions_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "sessions": [],
                "total_sessions": 0,
                "connected_sessions": 0,
                "error": "Failed to load public sessions dashboard",
            },
        )


@router.get("/sessions/{user_id}", response_class=HTMLResponse)
async def public_session_info(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Public session info page with energy cost management."""
    try:
        db_manager = get_database_manager()

        # Get user and session info
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get user's energy costs
        energy_costs = await db_manager.get_user_energy_costs(user_id)

        # Initialize default energy costs if user doesn't have any
        if not energy_costs:
            await db_manager.initialize_user_energy_costs(user_id)
            energy_costs = await db_manager.get_user_energy_costs(user_id)

        # Get user's badwords
        badwords = await db_manager.get_user_badwords(user_id)

        # Get user's whitelist words
        whitelist_words = await db_manager.get_user_whitelist_words(user_id)

        # Get user's autocorrect settings
        autocorrect_settings = await db_manager.get_autocorrect_settings(user_id)

        # Get user's custom redactions
        custom_redactions = await db_manager.get_user_custom_redactions(user_id)

        # Get connection status from telegram manager
        telegram_manager = get_telegram_manager()
        connected_users_info = await telegram_manager.get_connected_users()
        is_connected = user_id in {user["user_id"] for user in connected_users_info}

        # Get profile information if user is connected
        current_profile = None
        original_profile = None
        current_profile_photo_url = None
        original_profile_photo_url = None
        profile_revert_cost = await db_manager.get_profile_revert_cost(user_id)

        if is_connected:
            client_instance = telegram_manager.clients.get(user_id)
            if (
                client_instance
                and client_instance.profile_handler
                and client_instance.profile_handler.profile_manager
            ):
                current_profile = await client_instance.profile_handler.profile_manager.get_current_profile()
                original_profile = (
                    client_instance.profile_handler.profile_manager.original_profile
                )
                current_profile_photo_url = client_instance.profile_handler.profile_manager.get_profile_photo_url()
                original_profile_photo_url = client_instance.profile_handler.profile_manager.get_original_profile_photo_url()

        # Calculate current energy with recharge
        current_energy = user["energy"] if user["energy"] is not None else 100
        max_energy = user["max_energy"] if user["max_energy"] is not None else 100
        recharge_rate = (
            user["energy_recharge_rate"]
            if user["energy_recharge_rate"] is not None
            else 1
        )
        last_update = (
            datetime.fromisoformat(user["last_energy_update"])
            if user["last_energy_update"]
            else datetime.now()
        )

        # Calculate recharge
        now = datetime.now()
        time_diff = (now - last_update).total_seconds()
        energy_to_add = int(time_diff // 60) * recharge_rate
        current_energy = min(max_energy, current_energy + energy_to_add)

        # Get session timer information
        timer_info = await db_manager.get_session_timer_info(user_id)

        session_info = {
            "user_id": user["id"],
            "username": user["username"],
            "telegram_connected": bool(user["telegram_connected"]),
            "energy": current_energy,
            "max_energy": max_energy,
            "energy_percentage": int((current_energy / max_energy * 100))
            if max_energy > 0
            else 0,
            "energy_recharge_rate": recharge_rate,
            "last_energy_update": user["last_energy_update"],
            "account_created": user["created_at"],
            "display_name": user["username"],
            "is_connected": is_connected,
        }

        return templates.TemplateResponse(
            "session_info.html",
            {
                "request": request,
                "user": current_user,
                "session": session_info,
                "timer_info": timer_info,
                "energy_costs": energy_costs,
                "badwords": badwords,
                "whitelist_words": whitelist_words,
                "autocorrect_settings": autocorrect_settings,
                "custom_redactions": custom_redactions,
                "current_profile": current_profile,
                "original_profile": original_profile,
                "profile_revert_cost": profile_revert_cost,
                "current_profile_photo_url": current_profile_photo_url,
                "original_profile_photo_url": original_profile_photo_url,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading session info for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load session info")
