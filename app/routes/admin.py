"""Admin routes for user management."""

import logging
from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_database_manager
from app.auth import get_current_admin_user, get_password_hash

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_admin_user),
    success: str = None,
    error: str = None,
):
    """Admin dashboard showing user management."""
    try:
        db_manager = get_database_manager()

        # Get user statistics
        stats = await db_manager.get_user_stats()

        # Get all users
        users = await db_manager.get_all_users()

        return templates.TemplateResponse(
            "admin_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "stats": stats,
                "users": users,
                "success": success,
                "error": error,
            },
        )
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {e}")
        return templates.TemplateResponse(
            "admin_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "stats": {},
                "users": [],
                "error": "Failed to load admin data",
            },
        )


@router.post("/users/{user_id}/reset-password")
async def admin_reset_user_password(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_admin_user),
    new_password: str = Form(...),
):
    """Reset a user's password."""
    try:
        db_manager = get_database_manager()

        # Hash the new password
        hashed_password = get_password_hash(new_password)

        # Reset password
        success = await db_manager.reset_user_password(user_id, hashed_password)

        if success:
            logger.info(
                f"Admin {current_user['username']} reset password for user {user_id}"
            )
            return RedirectResponse(
                url="/admin?success=Password reset successfully",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url="/admin?error=Failed to reset password",
                status_code=303,
            )
    except Exception as e:
        logger.error(f"Error resetting password for user {user_id}: {e}")
        return RedirectResponse(
            url="/admin?error=Failed to reset password",
            status_code=303,
        )


@router.post("/users/{user_id}/toggle-admin")
async def admin_toggle_user_admin(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_admin_user),
):
    """Toggle admin status for a user."""
    try:
        # Prevent self-demotion
        if user_id == current_user["id"]:
            return RedirectResponse(
                url="/admin?error=Cannot modify your own admin status",
                status_code=303,
            )

        db_manager = get_database_manager()
        success = await db_manager.toggle_admin_status(user_id)

        if success:
            logger.info(
                f"Admin {current_user['username']} toggled admin status for user {user_id}"
            )
            return RedirectResponse(
                url="/admin?success=Admin status toggled successfully",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url="/admin?error=Failed to toggle admin status",
                status_code=303,
            )
    except Exception as e:
        logger.error(f"Error toggling admin status for user {user_id}: {e}")
        return RedirectResponse(
            url="/admin?error=Failed to toggle admin status",
            status_code=303,
        )


@router.post("/users/{user_id}/delete")
async def admin_delete_user(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_admin_user),
):
    """Delete a user and all associated data."""
    try:
        # Prevent self-deletion
        if user_id == current_user["id"]:
            return RedirectResponse(
                url="/admin?error=Cannot delete your own account",
                status_code=303,
            )

        db_manager = get_database_manager()

        # Get user info for logging
        user_info = await db_manager.get_user_by_id(user_id)
        if not user_info:
            return RedirectResponse(
                url="/admin?error=User not found",
                status_code=303,
            )

        # Delete user
        success = await db_manager.delete_user(user_id)

        if success:
            logger.info(
                f"Admin {current_user['username']} deleted user {user_info['username']} (ID: {user_id})"
            )
            return RedirectResponse(
                url="/admin?success=User deleted successfully",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url="/admin?error=Failed to delete user",
                status_code=303,
            )
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        return RedirectResponse(
            url="/admin?error=Failed to delete user",
            status_code=303,
        )


@router.post("/create-admin")
async def admin_create_admin(
    request: Request,
    current_user: dict = Depends(get_current_admin_user),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    """Create a new admin user."""
    try:
        db_manager = get_database_manager()

        # Check if user already exists
        existing_user = await db_manager.get_user_by_username(username)
        if existing_user:
            return RedirectResponse(
                url="/admin?error=Username already exists",
                status_code=303,
            )

        # Hash password and create admin user
        hashed_password = get_password_hash(password)
        user_id = await db_manager.create_admin_user(username, email, hashed_password)

        # Initialize default settings
        await db_manager.init_user_energy_costs(user_id)
        from app.database import init_user_profile_protection

        await init_user_profile_protection(user_id)

        logger.info(
            f"Admin {current_user['username']} created new admin user {username} (ID: {user_id})"
        )
        return RedirectResponse(
            url="/admin?success=Admin user created successfully",
            status_code=303,
        )
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        return RedirectResponse(
            url="/admin?error=Failed to create admin user",
            status_code=303,
        )
