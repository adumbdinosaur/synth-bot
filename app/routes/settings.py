"""Settings routes for energy, profile protection, and badwords management."""

import logging
from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_database_manager
from app.auth import get_current_user_with_session_check, get_current_user

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter()


# Energy Settings Routes
@router.get("/energy-settings", response_class=HTMLResponse)
async def energy_settings_page(
    request: Request, current_user: dict = Depends(get_current_user_with_session_check)
):
    """Energy settings configuration page."""
    try:
        db_manager = get_database_manager()

        # Get current energy costs for the user
        energy_costs = await db_manager.get_user_energy_costs(current_user["id"])

        # Get current energy info
        energy_info = await db_manager.get_user_energy(current_user["id"])

        return templates.TemplateResponse(
            "energy_settings.html",
            {
                "request": request,
                "user": current_user,
                "energy_costs": energy_costs,
                "current_energy": energy_info["energy"],
                "max_energy": energy_info["max_energy"],
            },
        )
    except Exception:
        return templates.TemplateResponse(
            "energy_settings.html",
            {
                "request": request,
                "user": current_user,
                "energy_costs": [],
                "current_energy": 0,
                "max_energy": 100,
                "error": "Failed to load energy settings",
            },
        )


@router.post("/energy-settings")
async def update_energy_settings(
    request: Request,
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Update energy cost settings."""
    try:
        form = await request.form()
        db_manager = get_database_manager()

        # Process each message type update
        for key, value in form.items():
            if key.endswith("_cost"):
                message_type = key.replace("_cost", "")
                try:
                    energy_cost = int(value)
                    if 0 <= energy_cost <= 100:  # Reasonable limits
                        description_key = f"{message_type}_description"
                        description = form.get(description_key, "")
                        await db_manager.update_user_energy_cost(
                            current_user["id"], message_type, energy_cost, description
                        )
                except ValueError:
                    continue  # Skip invalid values

        return RedirectResponse(url="/energy-settings?updated=true", status_code=303)

    except Exception as e:
        logger.error(f"Error updating energy settings: {e}")
        return RedirectResponse(
            url="/energy-settings?error=update_failed", status_code=303
        )


# Profile Protection Routes
@router.get("/profile-protection", response_class=HTMLResponse)
async def profile_protection_page(
    request: Request, current_user: dict = Depends(get_current_user_with_session_check)
):
    """Profile protection settings page."""
    try:
        db_manager = get_database_manager()

        # Get current profile protection settings
        penalty = await db_manager.get_profile_change_penalty(current_user["id"])
        is_locked = await db_manager.is_profile_locked(current_user["id"])
        original_profile = await db_manager.get_original_profile(current_user["id"])

        return templates.TemplateResponse(
            "profile_protection.html",
            {
                "request": request,
                "user": current_user,
                "profile_change_penalty": penalty,
                "is_profile_locked": is_locked,
                "original_profile": original_profile,
            },
        )
    except Exception as e:
        logger.error(f"Error loading profile protection settings: {e}")
        return templates.TemplateResponse(
            "profile_protection.html",
            {
                "request": request,
                "user": current_user,
                "profile_change_penalty": 10,
                "is_profile_locked": False,
                "original_profile": None,
                "error": "Failed to load profile protection settings",
            },
        )


@router.post("/profile-protection")
async def update_profile_protection_settings(
    request: Request,
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Update profile protection settings."""
    try:
        form = await request.form()
        db_manager = get_database_manager()

        # Update profile change penalty
        penalty_str = form.get("profile_change_penalty", "10")
        try:
            penalty = int(penalty_str)
            if 0 <= penalty <= 100:  # Reasonable limits
                await db_manager.set_profile_change_penalty(current_user["id"], penalty)
            else:
                raise ValueError("Penalty must be between 0 and 100")
        except ValueError as e:
            logger.error(f"Invalid penalty value: {e}")
            return RedirectResponse(
                url="/profile-protection?error=invalid_penalty", status_code=303
            )

        return RedirectResponse(url="/profile-protection?updated=true", status_code=303)

    except Exception as e:
        logger.error(f"Error updating profile protection settings: {e}")
        return RedirectResponse(
            url="/profile-protection?error=update_failed", status_code=303
        )


# Badwords Management Routes
@router.get("/badwords", response_class=HTMLResponse)
async def badwords_page(
    request: Request, current_user: dict = Depends(get_current_user_with_session_check)
):
    """Badwords management page."""
    try:
        db_manager = get_database_manager()

        # Get user's badwords
        badwords = await db_manager.get_user_badwords(current_user["id"])

        # Get current energy for display
        energy_info = await db_manager.get_user_energy(current_user["id"])

        return templates.TemplateResponse(
            "badwords.html",
            {
                "request": request,
                "user": current_user,
                "badwords": badwords,
                "current_energy": energy_info.get("energy", 0),
                "max_energy": 100,
            },
        )
    except Exception as e:
        logger.error(f"Error loading badwords page: {e}")
        return templates.TemplateResponse(
            "badwords.html",
            {
                "request": request,
                "user": current_user,
                "badwords": [],
                "current_energy": 0,
                "max_energy": 100,
                "error": "Failed to load badwords",
            },
        )


@router.post("/badwords/add")
async def add_badword(
    request: Request,
    word: str = Form(...),
    penalty: int = Form(5),
    case_sensitive: bool = Form(False),
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Add a new badword."""
    try:
        db_manager = get_database_manager()

        # Validate inputs
        word = word.strip()
        if not word:
            return RedirectResponse(url="/badwords?error=empty_word", status_code=303)

        if not (1 <= penalty <= 100):
            return RedirectResponse(
                url="/badwords?error=invalid_penalty", status_code=303
            )

        # Add the badword
        success = await db_manager.add_badword(
            current_user["id"], word, penalty, case_sensitive
        )

        if success:
            return RedirectResponse(url="/badwords?success=added", status_code=303)
        else:
            return RedirectResponse(url="/badwords?error=add_failed", status_code=303)

    except Exception as e:
        logger.error(f"Error adding badword: {e}")
        return RedirectResponse(url="/badwords?error=add_failed", status_code=303)


@router.post("/badwords/remove")
async def remove_badword(
    request: Request,
    word: str = Form(...),
    current_user: dict = Depends(get_current_user_with_session_check),
):
    """Remove a badword."""
    try:
        db_manager = get_database_manager()

        success = await db_manager.remove_badword(current_user["id"], word)

        if success:
            return RedirectResponse(url="/badwords?success=removed", status_code=303)
        else:
            return RedirectResponse(
                url="/badwords?error=remove_failed", status_code=303
            )

    except Exception as e:
        logger.error(f"Error removing badword: {e}")
        return RedirectResponse(url="/badwords?error=remove_failed", status_code=303)


@router.post("/badwords/update")
async def update_badword(
    request: Request,
    word: str = Form(...),
    penalty: int = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """Update badword penalty."""
    try:
        db_manager = get_database_manager()

        # Validate penalty
        if not (1 <= penalty <= 100):
            return RedirectResponse(
                url="/badwords?error=invalid_penalty", status_code=303
            )

        success = await db_manager.update_badword_penalty(
            current_user["id"], word, penalty
        )

        if success:
            return RedirectResponse(url="/badwords?success=updated", status_code=303)
        else:
            return RedirectResponse(
                url="/badwords?error=update_failed", status_code=303
            )

    except Exception as e:
        logger.error(f"Error updating badword: {e}")
        return RedirectResponse(url="/badwords?error=update_failed", status_code=303)
