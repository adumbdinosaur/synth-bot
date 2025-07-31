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
