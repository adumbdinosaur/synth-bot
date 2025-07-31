"""Dashboard routes for user main interface."""

import os
import logging
from fastapi import APIRouter, Request, Depends
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

            return templates.TemplateResponse(
                "dashboard_restricted.html",
                {
                    "request": request,
                    "user": current_user,
                    "energy_level": energy_info["energy"],
                    "max_energy": energy_info["max_energy"],
                    "recharge_rate": recharge_rate,
                    "recent_activities": recent_activities,
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
