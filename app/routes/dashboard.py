"""Dashboard routes for user main interface."""

import os
import logging
from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_database_manager
from app.auth import get_current_user
from app.telegram_client import get_telegram_manager
from app.energy_simple import EnergyManager

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
    message: str = None,
    message_type: str = None,
):
    """Main dashboard for authenticated users."""
    logger.info(f"Dashboard accessed by user {current_user['id']}")
    try:
        db_manager = get_database_manager()
        logger.info("Got database manager")

        # Check if user has active Telegram session
        has_active_session = await db_manager.has_active_telegram_session(
            current_user["id"]
        )
        logger.info(f"Has active session: {has_active_session}")

        # If user has active session, show restricted dashboard
        if has_active_session:
            logger.info("Showing restricted dashboard")
            # Get minimal info for restricted view
            energy_manager = EnergyManager()
            energy_info = await energy_manager.get_user_energy(current_user["id"])

            # Get user data for recharge rate
            user_data = await db_manager.get_user_by_id(current_user["id"])
            recharge_rate = user_data.get("energy_recharge_rate", 1) if user_data else 1

            # Get recent activity for the user
            try:
                recent_activities = await db_manager.get_recent_activity(
                    current_user["id"], limit=5
                )
            except Exception as e:
                logger.error(
                    f"Error getting recent activity for restricted dashboard: {e}"
                )
                recent_activities = []
            # Check if user's profile is locked (for chat list access)
            is_profile_locked = await db_manager.is_profile_locked(current_user["id"])
            logger.info(f"Profile locked (restricted dashboard): {is_profile_locked}")

            # Get session timer information
            timer_info = await db_manager.get_session_timer_info(current_user["id"])
            logger.info(f"Session timer info: {timer_info}")

            # Get chat list data if profile is locked
            chat_list = []
            list_mode = "blacklist"
            if is_profile_locked:
                list_mode = await db_manager.get_user_chat_list_mode(current_user["id"])
                if list_mode == "blacklist":
                    chat_list = await db_manager.get_user_blacklisted_chats(current_user["id"])
                else:  # whitelist
                    chat_list = await db_manager.get_user_whitelisted_chats(current_user["id"])
                logger.info(f"Chat list ({list_mode}): {len(chat_list)}")

            return templates.TemplateResponse(
                "dashboard_restricted.html",
                {
                    "request": request,
                    "user": current_user,
                    "energy_level": energy_info["energy"],
                    "max_energy": energy_info["max_energy"],
                    "recharge_rate": recharge_rate,
                    "recent_activities": recent_activities,
                    "is_profile_locked": is_profile_locked,
                    "chat_list": chat_list,
                    "list_mode": list_mode,
                    "blacklisted_chats": chat_list if list_mode == "blacklist" else [],  # For backwards compatibility
                    "whitelisted_chats": chat_list if list_mode == "whitelist" else [],
                    "timer_info": timer_info,
                    "message": message,
                    "message_type": message_type or "info",
                },
            )

        logger.info("Showing regular dashboard")
        # Regular dashboard for users without active sessions
        # Get user's Telegram connection status
        user_data = await db_manager.get_user_by_id(current_user["id"])
        logger.info(f"Got user data: {user_data is not None}")

        # Get client connection status from manager
        telegram_manager = get_telegram_manager()
        logger.info("Got telegram manager")

        client = await telegram_manager.get_client(current_user["id"])
        logger.info(f"Got client: {client is not None}")

        is_client_connected = False
        if client is not None:
            try:
                is_connected = client.is_connected  # Property, not method
                is_auth = await client.is_fully_authenticated()
                is_client_connected = is_connected and is_auth
                logger.info(f"Client connected: {is_client_connected}")
            except Exception as e:
                logger.error(f"Error checking client status: {e}")

        # Get system statistics
        telegram_manager = get_telegram_manager()
        logger.info("Getting connected users...")
        connected_users = await telegram_manager.get_connected_users()
        logger.info(f"Got {len(connected_users)} connected users")

        logger.info("Getting client count...")
        total_active_clients = telegram_manager.get_client_count()
        logger.info(f"Got {total_active_clients} total clients")

        # Check for session files for this user
        user_id = current_user["id"]
        session_files = []
        if os.path.exists("sessions"):
            for filename in os.listdir("sessions"):
                if filename.startswith(f"user_{user_id}_") and filename.endswith(
                    ".session"
                ):
                    session_files.append(filename)
        logger.info(f"Found {len(session_files)} session files")

        # Get user's energy level
        logger.info("Getting energy info...")
        energy_manager = EnergyManager()
        energy_info = await energy_manager.get_user_energy(user_id)
        energy_level = energy_info["energy"]
        max_energy = energy_info["max_energy"]
        energy_percentage = (
            int((energy_level / max_energy * 100)) if max_energy > 0 else 0
        )
        logger.info(f"Energy: {energy_level}/{max_energy}")

        # Check if user's profile is locked
        logger.info("Checking profile lock status...")
        is_profile_locked = await db_manager.is_profile_locked(user_id)
        logger.info(f"Profile locked: {is_profile_locked}")

        # Check if current user is in connected users list
        user_in_connected = any(
            user["user_id"] == current_user["id"] for user in connected_users
        )
        logger.info(f"User in connected: {user_in_connected}")

        # Get recent activity for the user
        logger.info("Getting recent activity...")
        try:
            recent_activities = await db_manager.get_recent_activity(user_id, limit=5)
        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            recent_activities = []

        logger.info("Rendering template...")
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": current_user,
                "telegram_connected": user_data["telegram_connected"]
                if user_data
                else False,
                "phone_number": user_data["phone_number"] if user_data else None,
                "client_connected": is_client_connected,
                "total_active_users": len(connected_users),
                "total_clients": total_active_clients,
                "user_in_connected": user_in_connected,
                "session_files_count": len(session_files),
                "has_session_files": len(session_files) > 0,
                "energy_level": energy_level,
                "max_energy": max_energy,
                "energy_percentage": energy_percentage,
                "recent_activities": recent_activities,
                "is_profile_locked": is_profile_locked,
                "message": message,
                "message_type": message_type or "info",
            },
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        import traceback

        traceback.print_exc()
        raise


@router.post("/disconnect-session")
async def disconnect_session(
    request: Request, current_user: dict = Depends(get_current_user)
):
    """Disconnect active Telegram session for users with restricted dashboard access."""
    try:
        user_id = current_user["id"]
        username = current_user["username"]

        # Disconnect any active Telegram client for this user
        session_disconnected = False
        try:
            telegram_manager = get_telegram_manager()
            if telegram_manager:
                client = await telegram_manager.get_client(user_id)
                if client is not None:
                    if client.is_connected:
                        await client.disconnect()
                        session_disconnected = True
                        logger.info(
                            f"Disconnected active Telegram client for user {user_id} ({username})"
                        )

                    # Remove from manager
                    if (
                        hasattr(telegram_manager, "clients")
                        and user_id in telegram_manager.clients
                    ):
                        del telegram_manager.clients[user_id]
                        logger.info(
                            f"Removed client from manager for user {user_id} ({username})"
                        )
        except Exception as e:
            logger.error(f"Error disconnecting client for user {user_id}: {e}")

        # Also delete session files to prevent auto-reconnection
        sessions_dir = "sessions"
        deleted_files = []

        if os.path.exists(sessions_dir):
            for filename in os.listdir(sessions_dir):
                if filename.startswith(f"user_{user_id}_") and filename.endswith(
                    ".session"
                ):
                    file_path = os.path.join(sessions_dir, filename)
                    try:
                        os.remove(file_path)
                        deleted_files.append(filename)
                        logger.info(
                            f"Deleted session file: {filename} for user {user_id} ({username})"
                        )
                    except Exception as e:
                        logger.error(f"Failed to delete session file {filename}: {e}")

        if session_disconnected or deleted_files:
            message = "Telegram session disconnected successfully. You now have full access to dashboard features."
            message_type = "success"
            logger.info(
                f"Session disconnection completed for user {user_id} ({username})"
            )
        else:
            message = "No active session found to disconnect."
            message_type = "info"
            logger.info(f"No active session found for user {user_id} ({username})")

        return RedirectResponse(
            url=f"/dashboard?message={message}&type={message_type}", status_code=302
        )

    except Exception as e:
        logger.error(f"Error disconnecting session for user {current_user['id']}: {e}")
        return RedirectResponse(
            url=f"/dashboard?message=Failed to disconnect session: {str(e)}&type=error",
            status_code=302,
        )


# Chat List Management Routes for Restricted Dashboard (blacklist/whitelist)
@router.post("/restricted-dashboard/chat-blacklist/add")
async def restricted_add_chat_to_list(
    request: Request,
    chat_id: int = Form(...),
    chat_title: str = Form(""),
    chat_type: str = Form(""),
    current_user: dict = Depends(get_current_user),
):
    """Add a chat to blacklist or whitelist from restricted dashboard."""
    try:
        db_manager = get_database_manager()

        # Check if user has active session (restricted dashboard requirement)
        has_active_session = await db_manager.has_active_telegram_session(
            current_user["id"]
        )
        if not has_active_session:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Check if user has a locked profile
        is_locked = await db_manager.is_profile_locked(current_user["id"])
        if not is_locked:
            return RedirectResponse(
                url="/dashboard?message=Chat list management is only available for users with locked profiles&type=error",
                status_code=302,
            )

        # Validate chat_id
        if chat_id == 0:
            return RedirectResponse(
                url="/dashboard?message=Please enter a valid chat ID&type=error",
                status_code=302,
            )

        # Clean up optional fields
        chat_title = chat_title.strip() if chat_title else None
        chat_type = chat_type.strip() if chat_type else None

        # Get user's current list mode and add to appropriate list
        list_mode = await db_manager.get_user_chat_list_mode(current_user["id"])
        
        if list_mode == "blacklist":
            success = await db_manager.add_blacklisted_chat(
                current_user["id"], chat_id, chat_title, chat_type
            )
            list_name = "blacklist"
        else:  # whitelist
            success = await db_manager.add_whitelisted_chat(
                current_user["id"], chat_id, chat_title, chat_type
            )
            list_name = "whitelist"

        if success:
            message = f"Chat {chat_id} added to {list_name} successfully"
            message_type = "success"
        else:
            message = f"Failed to add chat to {list_name}"
            message_type = "error"

    except Exception as e:
        logger.error(f"Error adding chat to list: {e}")
        message = "Failed to add chat to list"
        message_type = "error"

    return RedirectResponse(
        url=f"/dashboard?message={message}&type={message_type}", status_code=302
    )


@router.post("/restricted-dashboard/chat-blacklist/remove")
async def restricted_remove_chat_from_list(
    request: Request,
    chat_id: int = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """Remove a chat from blacklist or whitelist from restricted dashboard."""
    try:
        db_manager = get_database_manager()

        # Check if user has active session (restricted dashboard requirement)
        has_active_session = await db_manager.has_active_telegram_session(
            current_user["id"]
        )
        if not has_active_session:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Check if user has a locked profile
        is_locked = await db_manager.is_profile_locked(current_user["id"])
        if not is_locked:
            return RedirectResponse(
                url="/dashboard?message=Chat list management is only available for users with locked profiles&type=error",
                status_code=302,
            )

        # Get user's current list mode and remove from appropriate list
        list_mode = await db_manager.get_user_chat_list_mode(current_user["id"])
        
        if list_mode == "blacklist":
            success = await db_manager.remove_blacklisted_chat(current_user["id"], chat_id)
            list_name = "blacklist"
        else:  # whitelist
            success = await db_manager.remove_whitelisted_chat(current_user["id"], chat_id)
            list_name = "whitelist"

        if success:
            message = f"Chat {chat_id} removed from {list_name} successfully"
            message_type = "success"
        else:
            message = f"Failed to remove chat from {list_name}"
            message_type = "error"

    except Exception as e:
        logger.error(f"Error removing chat from list: {e}")
        message = "Failed to remove chat from list"
        message_type = "error"

    return RedirectResponse(
        url=f"/dashboard?message={message}&type={message_type}", status_code=302
    )


@router.post("/restricted-dashboard/chat-blacklist/toggle-mode")
async def restricted_toggle_chat_list_mode(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Toggle between blacklist and whitelist mode from restricted dashboard."""
    try:
        db_manager = get_database_manager()

        # Check if user has active session (restricted dashboard requirement)
        has_active_session = await db_manager.has_active_telegram_session(
            current_user["id"]
        )
        if not has_active_session:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Check if user has a locked profile
        is_locked = await db_manager.is_profile_locked(current_user["id"])
        if not is_locked:
            return RedirectResponse(
                url="/dashboard?message=Chat list management is only available for users with locked profiles&type=error",
                status_code=302,
            )

        # Get current mode
        current_mode = await db_manager.get_user_chat_list_mode(current_user["id"])
        new_mode = "whitelist" if current_mode == "blacklist" else "blacklist"

        # Clear the opposite list when switching modes
        if new_mode == "whitelist":
            # Switching to whitelist - clear blacklist
            await db_manager.clear_all_blacklisted_chats(current_user["id"])
        else:
            # Switching to blacklist - clear whitelist
            await db_manager.clear_all_whitelisted_chats(current_user["id"])

        # Set new mode
        success = await db_manager.set_user_chat_list_mode(current_user["id"], new_mode)

        if success:
            message = f"Successfully switched to {new_mode} mode! Your previous list has been cleared."
            message_type = "success"
        else:
            message = "Failed to switch list mode. Please try again."
            message_type = "error"

    except Exception as e:
        logger.error(f"Error toggling chat list mode from restricted dashboard: {e}")
        message = "Failed to switch list mode. Please try again."
        message_type = "error"

    return RedirectResponse(
        url=f"/dashboard?message={message}&type={message_type}", status_code=302
    )


@router.get("/api/session-timer-status")
async def session_timer_status(
    current_user: dict = Depends(get_current_user),
):
    """Get current session timer status for the logged-in user."""
    try:
        db_manager = get_database_manager()
        timer_info = await db_manager.get_session_timer_info(current_user["id"])
        
        if not timer_info:
            return {"has_timer": False, "timer_expired": True}
            
        return {
            "has_timer": timer_info["has_timer"],
            "timer_expired": timer_info["timer_expired"],
            "remaining_seconds": timer_info["remaining_seconds"],
            "timer_minutes": timer_info["timer_minutes"]
        }
        
    except Exception as e:
        logger.error(f"Error getting session timer status for user {current_user['id']}: {e}")
        return {"has_timer": False, "timer_expired": True, "error": str(e)}
