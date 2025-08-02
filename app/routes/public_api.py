"""Public API routes for controlling user sessions."""

import os
import time
import logging
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse

from app.database import get_database_manager
from app.auth import get_current_user_with_session_check
from app.telegram_client import get_telegram_manager
from app.energy_simple import EnergyManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public")


@router.post("/sessions/{user_id}/energy-costs")
async def update_session_energy_costs(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    text_cost: int = Form(None),
    photo_cost: int = Form(None),
    video_cost: int = Form(None),
    audio_cost: int = Form(None),
    voice_cost: int = Form(None),
    document_cost: int = Form(None),
    sticker_cost: int = Form(None),
    animation_cost: int = Form(None),
    gif_cost: int = Form(None),
    location_cost: int = Form(None),
    contact_cost: int = Form(None),
    poll_cost: int = Form(None),
    game_cost: int = Form(None),
    venue_cost: int = Form(None),
    web_page_cost: int = Form(None),
    media_group_cost: int = Form(None),
):
    """Update energy costs for all message types for a specific user."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Build cost mapping from form data, only including non-None values
        form_data = {
            "text": text_cost,
            "photo": photo_cost,
            "video": video_cost,
            "audio": audio_cost,
            "voice": voice_cost,
            "document": document_cost,
            "sticker": sticker_cost,
            "animation": animation_cost,
            "gif": gif_cost,
            "location": location_cost,
            "contact": contact_cost,
            "poll": poll_cost,
            "game": game_cost,
            "venue": venue_cost,
            "web_page": web_page_cost,
            "media_group": media_group_cost,
        }

        # Update each cost that was provided in the form
        for message_type, cost in form_data.items():
            if (
                cost is not None and cost >= 0
            ):  # Only update if cost is provided and non-negative
                await db_manager.update_user_energy_cost(user_id, message_type, cost)

        logger.info(f"Updated energy costs for user {user_id}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?success=Energy costs updated successfully",
            status_code=303,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating energy costs for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update energy costs",
            status_code=303,
        )


@router.post("/sessions/{user_id}/recharge-rate")
async def update_session_recharge_rate(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    recharge_rate: int = Form(...),
):
    """Update energy recharge rate for a specific user via public dashboard."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate recharge rate (allow 0-10 energy per minute)
        if not (0 <= recharge_rate <= 10):
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Recharge rate must be between 0 and 10 energy per minute",
                status_code=303,
            )

        # Update the recharge rate
        result = await db_manager.update_user_energy_recharge_rate(
            user_id, recharge_rate
        )

        if result["success"]:
            logger.info(f"Updated recharge rate for user {user_id} to {recharge_rate}")
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Energy recharge rate updated to {recharge_rate} per minute",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error={result['error']}",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating recharge rate for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update recharge rate",
            status_code=303,
        )


@router.post("/sessions/{user_id}/energy/add")
async def add_user_energy(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    amount: int = Form(...),
):
    """Add energy to a user via public dashboard."""
    try:
        energy_manager = EnergyManager()

        # Verify user exists
        db_manager = get_database_manager()
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate amount
        if amount <= 0:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Amount must be positive",
                status_code=303,
            )

        # Add energy
        result = await energy_manager.add_energy(user_id, amount)

        if result["success"]:
            logger.info(f"Added {amount} energy to user {user_id}")
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Added {amount} energy. Current: {result['energy']}/{result['max_energy']}",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to add energy",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding energy for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to add energy",
            status_code=303,
        )


@router.post("/sessions/{user_id}/energy/remove")
async def remove_user_energy(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    amount: int = Form(...),
):
    """Remove energy from a user via public dashboard."""
    try:
        energy_manager = EnergyManager()

        # Verify user exists
        db_manager = get_database_manager()
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Remove energy
        result = await energy_manager.remove_energy(user_id, amount)

        if result["success"]:
            logger.info(f"Removed {amount} energy from user {user_id}")
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Removed {amount} energy. Current: {result['energy']}/{result['max_energy']}",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error={result.get('error', 'Failed to remove energy')}",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing energy for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to remove energy",
            status_code=303,
        )


@router.post("/sessions/{user_id}/energy/set")
async def set_user_energy_level(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    energy_level: int = Form(...),
):
    """Set exact energy level for a user via public dashboard."""
    try:
        energy_manager = EnergyManager()

        # Verify user exists
        db_manager = get_database_manager()
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Set energy level
        result = await energy_manager.set_energy(user_id, energy_level)

        if result["success"]:
            logger.info(f"Set energy to {energy_level} for user {user_id}")
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Energy set to {result['energy']}/{result['max_energy']}",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error={result.get('error', 'Failed to set energy')}",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting energy for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to set energy",
            status_code=303,
        )


@router.post("/sessions/{user_id}/energy/max-energy")
async def update_user_max_energy_level(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    max_energy: int = Form(...),
):
    """Update maximum energy for a user via public dashboard."""
    try:
        energy_manager = EnergyManager()

        # Verify user exists
        db_manager = get_database_manager()
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update max energy
        result = await energy_manager.update_max_energy(user_id, max_energy)

        if result["success"]:
            logger.info(f"Updated max energy to {max_energy} for user {user_id}")
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Maximum energy updated to {result['max_energy']}. Current: {result['current_energy']}/{result['max_energy']}",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error={result.get('error', 'Failed to update maximum energy')}",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating max energy for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update maximum energy",
            status_code=303,
        )


@router.post("/sessions/{user_id}/profile/update")
async def update_user_profile(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    first_name: str = Form(None),
    last_name: str = Form(None),
    bio: str = Form(None),
    profile_photo: UploadFile = File(None),
):
    """Update user profile via ProfileManager - costs no energy and always saves as new state."""
    try:
        db_manager = get_database_manager()
        telegram_manager = get_telegram_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get the user's telegram client
        client_instance = telegram_manager.clients.get(user_id)
        if (
            not client_instance
            or not client_instance.profile_handler
            or not client_instance.profile_handler.profile_manager
        ):
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=User not connected or profile manager not available",
                status_code=303,
            )

        # Handle profile photo upload if provided
        profile_photo_file = None
        if profile_photo and profile_photo.filename:
            # Validate file type
            if not profile_photo.content_type.startswith("image/"):
                return RedirectResponse(
                    url=f"/public/sessions/{user_id}?error=Invalid file type. Please upload an image file.",
                    status_code=303,
                )

            # Save uploaded file temporarily
            # Create temp directory if it doesn't exist
            temp_dir = os.path.join(os.getcwd(), "temp")
            os.makedirs(temp_dir, exist_ok=True)

            # Save file with original extension
            file_extension = os.path.splitext(profile_photo.filename)[1] or ".jpg"
            temp_filename = f"temp_profile_{user_id}_{int(time.time())}{file_extension}"
            profile_photo_file = os.path.join(temp_dir, temp_filename)

            try:
                # Save uploaded file
                with open(profile_photo_file, "wb") as temp_file:
                    content = await profile_photo.read()
                    temp_file.write(content)

                logger.info(
                    f"Saved uploaded profile photo temporarily to: {profile_photo_file}"
                )

            except Exception as e:
                logger.error(f"Error saving uploaded file: {e}")
                return RedirectResponse(
                    url=f"/public/sessions/{user_id}?error=Failed to save uploaded file",
                    status_code=303,
                )

        # Update the profile using ProfileManager
        success = await client_instance.profile_handler.profile_manager.update_profile(
            first_name=first_name if first_name else None,
            last_name=last_name if last_name else None,
            bio=bio if bio else None,
            profile_photo_file=profile_photo_file,
        )

        # Clean up temporary file if it was created
        if profile_photo_file and os.path.exists(profile_photo_file):
            try:
                os.remove(profile_photo_file)
                logger.info(f"Cleaned up temporary file: {profile_photo_file}")
            except Exception as e:
                logger.warning(
                    f"Failed to clean up temporary file {profile_photo_file}: {e}"
                )

        if not success:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to update profile",
                status_code=303,
            )

        # Always save the current state as the new original/saved state
        save_success = await client_instance.profile_handler.profile_manager.save_current_as_original()
        message = (
            "Profile updated and saved as new state"
            if save_success
            else "Profile updated but failed to save as new state"
        )

        return RedirectResponse(
            url=f"/public/sessions/{user_id}?success={message}",
            status_code=303,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update profile",
            status_code=303,
        )


@router.post("/sessions/{user_id}/badwords/add")
async def public_add_badword(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    word: str = Form(...),
    penalty: int = Form(5),
    case_sensitive: bool = Form(False),
):
    """Add a badword for a user via public dashboard."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate inputs
        word = word.strip()
        if not word:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Empty word not allowed",
                status_code=303,
            )

        if not (1 <= penalty <= 100):
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Penalty must be between 1 and 100",
                status_code=303,
            )

        # Add the badword
        success = await db_manager.add_badword(user_id, word, penalty, case_sensitive)

        if success:
            logger.info(
                f"Added badword '{word}' (penalty: {penalty}) for user {user_id}"
            )
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Badword '{word}' added successfully",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to add badword",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding badword for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to add badword",
            status_code=303,
        )


@router.post("/sessions/{user_id}/badwords/remove")
async def public_remove_badword(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    word: str = Form(...),
):
    """Remove a badword for a user via public dashboard."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Remove the badword
        success = await db_manager.remove_badword(user_id, word)

        if success:
            logger.info(f"Removed badword '{word}' for user {user_id}")
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Badword '{word}' removed successfully",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to remove badword - word may not exist",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing badword for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to remove badword",
            status_code=303,
        )


@router.post("/sessions/{user_id}/badwords/update")
async def public_update_badword_penalty(
    request: Request,
    user_id: int,
    word: str = Form(...),
    penalty: int = Form(...),
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Update the penalty for an existing badword via public dashboard."""
    try:
        db_manager = get_database_manager()

        # Validate penalty
        if penalty < 1 or penalty > 100:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Penalty must be between 1 and 100",
                status_code=302,
            )

        # Update the badword penalty
        success = await db_manager.update_badword_penalty(user_id, word, penalty)

        if success:
            logger.info(
                f"Updated badword '{word}' penalty to {penalty} for user {user_id}"
            )
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Badword '{word}' penalty updated successfully",
                status_code=302,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to update badword penalty",
                status_code=302,
            )

    except Exception as e:
        logger.error(f"Error updating badword penalty for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update badword penalty",
            status_code=302,
        )


@router.post("/sessions/{user_id}/autocorrect")
async def update_autocorrect_settings(
    request: Request,
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Update autocorrect settings for a specific user."""
    try:
        db_manager = get_database_manager()
        form = await request.form()

        # Handle checkbox for enabled - if not present in form, it means False
        # The checkbox sends value="true" when checked, nothing when unchecked
        enabled = "enabled" in form and form["enabled"] == "true"
        penalty_per_correction = int(form.get("penalty_per_correction", 5))

        # Validate penalty range
        if penalty_per_correction < 1 or penalty_per_correction > 50:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Penalty per correction must be between 1 and 50",
                status_code=303,
            )

        # Update autocorrect settings
        await db_manager.autocorrect.update_autocorrect_settings(
            user_id, enabled, penalty_per_correction
        )

        status_text = "enabled" if enabled else "disabled"
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?success=Autocorrect {status_text} successfully with {penalty_per_correction} energy penalty per correction",
            status_code=303,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating autocorrect settings for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update autocorrect settings",
            status_code=303,
        )


@router.get("/api/sessions")
async def get_sessions_api(
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """API endpoint to get public sessions data for AJAX updates."""
    try:
        db_manager = get_database_manager()
        telegram_manager = get_telegram_manager()

        # Get all sessions (including inactive ones for context)
        active_sessions = await db_manager.get_active_telegram_sessions()

        # Get list of connected user IDs from telegram manager
        connected_users = telegram_manager.get_connected_users()
        connected_users_by_id = {user["user_id"]: user for user in connected_users}

        # Enhance session data with connection status and display info
        for session in active_sessions:
            session["is_connected"] = session["user_id"] in connected_users_by_id

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

        return {
            "success": True,
            "sessions": active_sessions,
            "total_sessions": len(active_sessions),
            "connected_sessions": len(
                [s for s in active_sessions if s["is_connected"]]
            ),
        }
    except Exception as e:
        logger.error(f"Error getting sessions API data: {e}")
        return {
            "success": False,
            "error": "Failed to load sessions data",
            "sessions": [],
            "total_sessions": 0,
            "connected_sessions": 0,
        }


# JSON API endpoints for AJAX operations (no redirects)


@router.post("/api/sessions/{user_id}/energy/add")
async def add_user_energy_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    amount: int = Form(...),
):
    """Add energy to a user via AJAX."""
    try:
        energy_manager = EnergyManager()
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if amount <= 0:
            return {"success": False, "error": "Amount must be positive"}

        result = await energy_manager.add_energy(user_id, amount)

        if result["success"]:
            return {
                "success": True,
                "message": f"Added {amount} energy",
                "energy": result["energy"],
                "max_energy": result["max_energy"],
            }
        else:
            return {"success": False, "error": "Failed to add energy"}

    except Exception as e:
        logger.error(f"Error adding energy for user {user_id}: {e}")
        return {"success": False, "error": "Failed to add energy"}


@router.post("/api/sessions/{user_id}/energy/remove")
async def remove_user_energy_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    amount: int = Form(...),
):
    """Remove energy from a user via AJAX."""
    try:
        energy_manager = EnergyManager()
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if amount <= 0:
            return {"success": False, "error": "Amount must be positive"}

        result = await energy_manager.remove_energy(user_id, amount)

        if result["success"]:
            return {
                "success": True,
                "message": f"Removed {amount} energy",
                "energy": result["energy"],
                "max_energy": result["max_energy"],
            }
        else:
            return {"success": False, "error": "Failed to remove energy"}

    except Exception as e:
        logger.error(f"Error removing energy for user {user_id}: {e}")
        return {"success": False, "error": "Failed to remove energy"}


@router.post("/api/sessions/{user_id}/energy/set")
async def set_user_energy_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    energy_level: int = Form(...),
):
    """Set energy level for a user via AJAX."""
    try:
        energy_manager = EnergyManager()
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if energy_level < 0:
            return {"success": False, "error": "Energy level cannot be negative"}

        result = await energy_manager.set_energy(user_id, energy_level)

        if result["success"]:
            return {
                "success": True,
                "message": f"Set energy to {energy_level}",
                "energy": result["energy"],
                "max_energy": result["max_energy"],
            }
        else:
            return {"success": False, "error": "Failed to set energy level"}

    except Exception as e:
        logger.error(f"Error setting energy for user {user_id}: {e}")
        return {"success": False, "error": "Failed to set energy level"}


@router.post("/api/sessions/{user_id}/energy/max-energy")
async def set_max_energy_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    max_energy: int = Form(...),
):
    """Set max energy for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if max_energy <= 0:
            return {"success": False, "error": "Max energy must be positive"}

        await db_manager.update_user_max_energy(user_id, max_energy)

        # Get updated energy info
        energy_manager = EnergyManager()
        current_energy = await energy_manager.get_energy(user_id)

        return {
            "success": True,
            "message": f"Set max energy to {max_energy}",
            "energy": current_energy,
            "max_energy": max_energy,
        }

    except Exception as e:
        logger.error(f"Error setting max energy for user {user_id}: {e}")
        return {"success": False, "error": "Failed to set max energy"}


@router.post("/api/sessions/{user_id}/recharge-rate")
async def update_recharge_rate_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    recharge_rate: int = Form(...),
):
    """Update energy recharge rate for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if recharge_rate < 0 or recharge_rate > 10:
            return {"success": False, "error": "Recharge rate must be between 0 and 10"}

        await db_manager.update_user_energy_recharge_rate(user_id, recharge_rate)

        return {
            "success": True,
            "message": f"Set recharge rate to {recharge_rate} energy per minute",
            "recharge_rate": recharge_rate,
        }

    except Exception as e:
        logger.error(f"Error updating recharge rate for user {user_id}: {e}")
        return {"success": False, "error": "Failed to update recharge rate"}


@router.post("/api/sessions/{user_id}/badwords/add")
async def add_badword_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    word: str = Form(...),
    penalty: int = Form(...),
):
    """Add a badword for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if penalty < 1 or penalty > 100:
            return {"success": False, "error": "Penalty must be between 1 and 100"}

        if not word.strip():
            return {"success": False, "error": "Word cannot be empty"}

        success = await db_manager.add_badword(user_id, word.strip(), penalty)

        if success:
            return {
                "success": True,
                "message": f"Added badword '{word}' with penalty {penalty}",
                "word": word.strip(),
                "penalty": penalty,
            }
        else:
            return {"success": False, "error": "Failed to add badword"}

    except Exception as e:
        logger.error(f"Error adding badword for user {user_id}: {e}")
        return {"success": False, "error": "Failed to add badword"}


@router.post("/api/sessions/{user_id}/badwords/remove")
async def remove_badword_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    word: str = Form(...),
):
    """Remove a badword for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if not word.strip():
            return {"success": False, "error": "Word cannot be empty"}

        success = await db_manager.remove_badword(user_id, word.strip())

        if success:
            return {
                "success": True,
                "message": f"Removed badword '{word}'",
                "word": word.strip(),
            }
        else:
            return {"success": False, "error": "Failed to remove badword"}

    except Exception as e:
        logger.error(f"Error removing badword for user {user_id}: {e}")
        return {"success": False, "error": "Failed to remove badword"}


@router.post("/api/sessions/{user_id}/badwords/update")
async def update_badword_penalty_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    word: str = Form(...),
    penalty: int = Form(...),
):
    """Update badword penalty for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if penalty < 1 or penalty > 100:
            return {"success": False, "error": "Penalty must be between 1 and 100"}

        if not word.strip():
            return {"success": False, "error": "Word cannot be empty"}

        success = await db_manager.update_badword_penalty(
            user_id, word.strip(), penalty
        )

        if success:
            return {
                "success": True,
                "message": f"Updated badword '{word}' penalty to {penalty}",
                "word": word.strip(),
                "penalty": penalty,
            }
        else:
            return {"success": False, "error": "Failed to update badword penalty"}

    except Exception as e:
        logger.error(f"Error updating badword penalty for user {user_id}: {e}")
        return {"success": False, "error": "Failed to update badword penalty"}


@router.post("/api/sessions/{user_id}/autocorrect")
async def update_autocorrect_settings_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    enabled: str = Form(None),
    penalty_per_correction: int = Form(None),
):
    """Update autocorrect settings for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        # Get current settings first
        current_settings = await db_manager.get_autocorrect_settings(user_id)

        # Use current values as defaults
        new_enabled = current_settings.get("enabled", False)
        new_penalty = current_settings.get("penalty_per_correction", 5)

        updated_settings = {}

        # Update enabled status if provided
        if enabled is not None:
            new_enabled = enabled.lower() in ["true", "1", "on", "yes"]
            updated_settings["enabled"] = new_enabled

        # Update penalty if provided
        if penalty_per_correction is not None:
            if penalty_per_correction < 1 or penalty_per_correction > 100:
                return {"success": False, "error": "Penalty must be between 1 and 100"}
            new_penalty = penalty_per_correction
            updated_settings["penalty_per_correction"] = new_penalty

        if updated_settings:
            # Update both settings (the method requires both parameters)
            await db_manager.update_autocorrect_settings(
                user_id, new_enabled, new_penalty
            )

            message_parts = []
            if "enabled" in updated_settings:
                message_parts.append(
                    f"Autocorrect {'enabled' if updated_settings['enabled'] else 'disabled'}"
                )
            if "penalty_per_correction" in updated_settings:
                message_parts.append(
                    f"penalty set to {updated_settings['penalty_per_correction']}"
                )

            return {
                "success": True,
                "message": ", ".join(message_parts),
                **updated_settings,
            }
        else:
            return {"success": False, "error": "No settings to update"}

    except Exception as e:
        logger.error(f"Error updating autocorrect settings for user {user_id}: {e}")
        return {"success": False, "error": "Failed to update autocorrect settings"}


@router.post("/api/sessions/{user_id}/energy-costs")
async def update_session_energy_costs_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    text_cost: int = Form(None),
    photo_cost: int = Form(None),
    video_cost: int = Form(None),
    audio_cost: int = Form(None),
    voice_cost: int = Form(None),
    document_cost: int = Form(None),
    sticker_cost: int = Form(None),
    animation_cost: int = Form(None),
    gif_cost: int = Form(None),
    location_cost: int = Form(None),
    contact_cost: int = Form(None),
    poll_cost: int = Form(None),
    game_cost: int = Form(None),
    venue_cost: int = Form(None),
    web_page_cost: int = Form(None),
    media_group_cost: int = Form(None),
):
    """Update energy costs for all message types for a specific user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        # Build cost mapping from form data, only including non-None values
        form_data = {
            "text": text_cost,
            "photo": photo_cost,
            "video": video_cost,
            "audio": audio_cost,
            "voice": voice_cost,
            "document": document_cost,
            "sticker": sticker_cost,
            "animation": animation_cost,
            "gif": gif_cost,
            "location": location_cost,
            "contact": contact_cost,
            "poll": poll_cost,
            "game": game_cost,
            "venue": venue_cost,
            "web_page": web_page_cost,
            "media_group": media_group_cost,
        }

        updated_costs = {}
        # Update each cost that was provided in the form
        for message_type, cost in form_data.items():
            if cost is not None and cost >= 0:
                await db_manager.update_user_energy_cost(user_id, message_type, cost)
                updated_costs[message_type] = cost

        return {
            "success": True,
            "message": f"Updated energy costs for {len(updated_costs)} message types",
            "updated_costs": updated_costs,
        }

    except Exception as e:
        logger.error(f"Error updating energy costs for user {user_id}: {e}")
        return {"success": False, "error": "Failed to update energy costs"}


@router.post("/api/sessions/{user_id}/profile/revert-cost")
async def update_profile_revert_cost_json(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
    revert_cost: int = Form(...),
):
    """Update profile revert cost for a user via AJAX."""
    try:
        db_manager = get_database_manager()

        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if revert_cost < 0 or revert_cost > 100:
            return {"success": False, "error": "Revert cost must be between 0 and 100"}

        # Update the profile revert cost in the database
        # Assuming there's a method to update this, if not we may need to add it
        try:
            await db_manager.update_user_profile_revert_cost(user_id, revert_cost)
            return {
                "success": True,
                "message": f"Profile revert cost updated to {revert_cost} energy",
                "revert_cost": revert_cost,
            }
        except AttributeError:
            # If the method doesn't exist, we'll update it directly
            # This is a fallback - you may need to implement the proper method
            return {
                "success": False,
                "error": "Profile revert cost update not implemented",
            }

    except Exception as e:
        logger.error(f"Error updating profile revert cost for user {user_id}: {e}")
        return {"success": False, "error": "Failed to update profile revert cost"}


# Custom Redactions Management Endpoints


@router.post("/sessions/{user_id}/custom_redactions")
async def add_custom_redaction(
    user_id: int,
    original_word: str = Form(...),
    replacement_word: str = Form(...),
    penalty: int = Form(5),
    case_sensitive: bool = Form(False),
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Add a custom redaction for a user."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        # Validate input
        if not original_word.strip() or not replacement_word.strip():
            return {
                "success": False,
                "error": "Original word and replacement word cannot be empty",
            }

        if penalty < 1 or penalty > 100:
            return {"success": False, "error": "Penalty must be between 1 and 100"}

        # Add custom redaction
        success = await db_manager.add_custom_redaction(
            user_id,
            original_word.strip(),
            replacement_word.strip(),
            penalty,
            case_sensitive,
        )

        if success:
            # Get the added redaction to return
            redactions = await db_manager.get_user_custom_redactions(user_id)
            added_redaction = next(
                (r for r in redactions if r["original_word"] == original_word.strip()),
                None,
            )

            logger.info(
                f"Added custom redaction '{original_word}' -> '{replacement_word}' for user {user_id}"
            )
            return {
                "success": True,
                "message": "Custom redaction added successfully",
                "redaction": added_redaction,
            }
        else:
            return {"success": False, "error": "Failed to add custom redaction"}

    except Exception as e:
        logger.error(f"Error adding custom redaction for user {user_id}: {e}")
        return {"success": False, "error": "Failed to add custom redaction"}


@router.put("/sessions/{user_id}/custom_redactions/{original_word}")
async def update_custom_redaction(
    user_id: int,
    original_word: str,
    replacement_word: str = Form(None),
    penalty: int = Form(None),
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Update a custom redaction for a user."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        # Validate input
        if replacement_word is not None and not replacement_word.strip():
            return {"success": False, "error": "Replacement word cannot be empty"}

        if penalty is not None and (penalty < 1 or penalty > 100):
            return {"success": False, "error": "Penalty must be between 1 and 100"}

        # Update custom redaction
        success = await db_manager.update_custom_redaction(
            user_id,
            original_word,
            replacement_word.strip() if replacement_word else None,
            penalty,
        )

        if success:
            # Get the updated redaction
            redactions = await db_manager.get_user_custom_redactions(user_id)
            updated_redaction = next(
                (r for r in redactions if r["original_word"] == original_word), None
            )

            logger.info(
                f"Updated custom redaction '{original_word}' for user {user_id}"
            )
            return {
                "success": True,
                "message": "Custom redaction updated successfully",
                "redaction": updated_redaction,
            }
        else:
            return {
                "success": False,
                "error": "Custom redaction not found or failed to update",
            }

    except Exception as e:
        logger.error(f"Error updating custom redaction for user {user_id}: {e}")
        return {"success": False, "error": "Failed to update custom redaction"}


@router.delete("/sessions/{user_id}/custom_redactions/{original_word}")
async def remove_custom_redaction(
    user_id: int,
    original_word: str,
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Remove a custom redaction for a user."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        # Remove custom redaction
        success = await db_manager.remove_custom_redaction(user_id, original_word)

        if success:
            logger.info(
                f"Removed custom redaction '{original_word}' for user {user_id}"
            )
            return {"success": True, "message": "Custom redaction removed successfully"}
        else:
            return {"success": False, "error": "Custom redaction not found"}

    except Exception as e:
        logger.error(f"Error removing custom redaction for user {user_id}: {e}")
        return {"success": False, "error": "Failed to remove custom redaction"}


@router.get("/sessions/{user_id}/custom_redactions")
async def get_custom_redactions(
    user_id: int,
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Get all custom redactions for a user."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        # Get custom redactions
        redactions = await db_manager.get_user_custom_redactions(user_id)
        statistics = await db_manager.get_redaction_statistics(user_id)

        return {"success": True, "redactions": redactions, "statistics": statistics}

    except Exception as e:
        logger.error(f"Error getting custom redactions for user {user_id}: {e}")
        return {"success": False, "error": "Failed to get custom redactions"}
