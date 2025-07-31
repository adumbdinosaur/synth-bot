"""Telegram connection and authentication routes."""

import os
import logging
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_database_manager
from app.auth import get_current_user
from app.telegram_client import get_telegram_manager

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/telegram")


@router.get("/connect", response_class=HTMLResponse)
async def telegram_connect_page(
    request: Request, current_user: dict = Depends(get_current_user), error: str = None
):
    """Telegram connection page."""
    # Handle specific error messages
    error_message = None
    if error == "session_expired":
        error_message = "Your session expired. Please reconnect your Telegram account."
    elif error == "invalid_state":
        error_message = "Authentication state is invalid. Please start the connection process again."
    elif error:
        error_message = error

    return templates.TemplateResponse(
        "telegram_connect.html",
        {"request": request, "user": current_user, "error": error_message},
    )


@router.post("/connect")
async def telegram_connect(
    request: Request,
    phone_number: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """Handle Telegram connection request."""
    try:
        # Get or create Telegram client using manager
        telegram_manager = get_telegram_manager()
        client = await telegram_manager.get_or_create_client(
            user_id=current_user["id"],
            username=current_user["username"],
            phone_number=phone_number,
        )

        # Send code request
        result = await client.send_code_request()
        if result.get("success"):
            logger.info(
                f"Code sent successfully for user {current_user['id']} ({current_user['username']})"
            )

            # Check if already authorized
            if result.get("already_authorized"):
                return RedirectResponse(
                    url="/dashboard?message=already_connected", status_code=302
                )

            # Prepare template context with delivery information
            template_context = {
                "request": request,
                "user": current_user,
                "phone_number": phone_number,
            }

            # Add delivery method information
            delivery_method = result.get("delivery_method", "unknown")
            if delivery_method == "telegram_app":
                template_context["delivery_info"] = (
                    "Check your Telegram app for the verification code"
                )
                template_context["delivery_icon"] = "fab fa-telegram-plane"
            elif delivery_method == "sms":
                template_context["delivery_info"] = (
                    "Check your SMS messages for the verification code"
                )
                template_context["delivery_icon"] = "fas fa-sms"
            elif delivery_method == "phone_call":
                template_context["delivery_info"] = (
                    "You will receive a phone call with the verification code"
                )
                template_context["delivery_icon"] = "fas fa-phone"
            else:
                template_context["delivery_info"] = (
                    "Check your phone for the verification code"
                )
                template_context["delivery_icon"] = "fas fa-mobile-alt"

            template_context["code_length"] = result.get("code_length", 5)

            return templates.TemplateResponse("telegram_verify.html", template_context)
        else:
            return templates.TemplateResponse(
                "telegram_connect.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Failed to send verification code",
                },
            )
    except Exception as e:
        logger.error(f"Error in telegram connect for user {current_user['id']}: {e}")
        return templates.TemplateResponse(
            "telegram_connect.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Connection failed: {str(e)}",
            },
        )


@router.post("/verify")
async def telegram_verify(
    request: Request,
    code: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """Handle Telegram code verification."""
    try:
        # Get client from manager
        telegram_manager = get_telegram_manager()
        client = await telegram_manager.get_client(current_user["id"])
        if not client:
            logger.warning(
                f"No client found for user {current_user['id']} during verification - attempting to recreate"
            )

            # Try to get the phone number from the database
            db_manager = get_database_manager()
            user_data = await db_manager.get_user_by_id(current_user["id"])
            phone_number = (
                user_data["phone_number"]
                if user_data and user_data["phone_number"]
                else None
            )

            if not phone_number:
                logger.error(
                    f"No phone number found for user {current_user['id']} - redirecting to connect"
                )
                return RedirectResponse(
                    url="/telegram/connect?error=session_expired", status_code=302
                )

            # Recreate client with existing session
            telegram_manager = get_telegram_manager()
            client = await telegram_manager.get_or_create_client(
                user_id=current_user["id"],
                username=current_user["username"],
                phone_number=phone_number,
            )
            logger.info(
                f"Recreated client for user {current_user['id']} with phone {phone_number}"
            )

        # Log the verification attempt
        logger.info(
            f"Attempting code verification for user {current_user['id']} ({current_user['username']})"
        )

        # Verify code only (first step)
        result = await client.verify_code(code)

        logger.info(
            f"Code verification result for user {current_user['id']}: success={result.get('success')}, requires_2fa={result.get('requires_2fa')}"
        )

        if result["success"] and not result.get("requires_2fa"):
            # Code verified successfully and no 2FA required - complete authentication
            logger.info(
                f"Code verification complete for user {current_user['id']} - no 2FA required"
            )
            db_manager = get_database_manager()
            await db_manager.update_user_telegram_info(
                current_user["id"], client.phone_number, True
            )

            # Start message listener in background
            listener_started = await client.start_message_listener()
            if listener_started:
                logger.info(
                    f"Message listener started for user {current_user['id']} ({current_user['username']})"
                )
            else:
                logger.error(
                    f"Failed to start message listener for user {current_user['id']} ({current_user['username']})"
                )

            return RedirectResponse(
                url="/dashboard?message=Telegram connected successfully&type=success",
                status_code=302,
            )

        elif result["success"] and result.get("requires_2fa"):
            # Code verified but 2FA is required - redirect to 2FA form
            logger.info(
                f"Code verified for user {current_user['id']} - redirecting to 2FA verification"
            )
            return templates.TemplateResponse(
                "telegram_2fa.html",
                {
                    "request": request,
                    "user": current_user,
                    "phone_number": client.phone_number,
                },
            )

        else:
            # Code verification failed
            logger.warning(
                f"Code verification failed for user {current_user['id']}: {result.get('error')}"
            )
            return templates.TemplateResponse(
                "telegram_verify.html",
                {
                    "request": request,
                    "user": current_user,
                    "phone_number": client.phone_number,
                    "error": result.get("error", "Invalid verification code"),
                },
            )

    except Exception as e:
        logger.error(
            f"Error during code verification for user {current_user['id']}: {e}"
        )
        import traceback

        traceback.print_exc()
        return templates.TemplateResponse(
            "telegram_verify.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Verification failed: {str(e)}",
            },
        )


@router.post("/verify-2fa")
async def telegram_verify_2fa(
    request: Request,
    password: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """Handle Telegram 2FA verification."""
    try:
        # Get client from manager
        telegram_manager = get_telegram_manager()
        client = await telegram_manager.get_client(current_user["id"])
        if not client:
            logger.warning(
                f"No client found for user {current_user['id']} during 2FA verification"
            )
            return RedirectResponse(
                url="/telegram/connect?error=session_expired", status_code=302
            )

        # Check if client is in the correct state for 2FA
        auth_state = client.get_auth_state()
        logger.info(
            f"2FA verification attempt for user {current_user['id']} - auth state: {auth_state}"
        )

        if auth_state != "requires_2fa":
            logger.warning(
                f"Invalid auth state for 2FA verification for user {current_user['id']}: {auth_state}"
            )
            # Try to reconnect and check state
            if auth_state == "authenticated":
                # Already authenticated, redirect to dashboard
                return RedirectResponse(
                    url="/dashboard?message=Already authenticated&type=info",
                    status_code=302,
                )
            else:
                # Need to restart authentication
                return RedirectResponse(
                    url="/telegram/connect?error=invalid_state", status_code=302
                )

        # Verify 2FA password
        logger.info(
            f"Attempting 2FA password verification for user {current_user['id']}"
        )
        success = await client.verify_2fa_password(password)

        if success:
            # 2FA verified successfully - complete authentication
            logger.info(f"2FA verification successful for user {current_user['id']}")
            db_manager = get_database_manager()
            await db_manager.update_user_telegram_info(
                current_user["id"], client.phone_number, True
            )

            # Start message listener in background
            listener_started = await client.start_message_listener()
            if listener_started:
                logger.info(
                    f"Message listener started for user {current_user['id']} ({current_user['username']})"
                )
            else:
                logger.error(
                    f"Failed to start message listener for user {current_user['id']} ({current_user['username']})"
                )

            return RedirectResponse(
                url="/dashboard?message=Telegram connected successfully with 2FA&type=success",
                status_code=302,
            )
        else:
            # 2FA verification failed
            logger.warning(f"2FA verification failed for user {current_user['id']}")
            return templates.TemplateResponse(
                "telegram_2fa.html",
                {
                    "request": request,
                    "user": current_user,
                    "phone_number": client.phone_number,
                    "error": "Invalid password. Please try again.",
                },
            )
    except Exception as e:
        logger.error(
            f"Error during 2FA verification for user {current_user['id']}: {e}"
        )
        import traceback

        traceback.print_exc()
        return templates.TemplateResponse(
            "telegram_2fa.html",
            {
                "request": request,
                "user": current_user,
                "error": f"2FA verification failed: {str(e)}",
            },
        )


@router.post("/disconnect")
async def telegram_disconnect(current_user: dict = Depends(get_current_user)):
    """Disconnect Telegram client."""
    try:
        # Remove client from manager
        telegram_manager = get_telegram_manager()
        await telegram_manager.remove_client(current_user["id"])
        logger.info(
            f"Disconnected Telegram client for user {current_user['id']} ({current_user['username']})"
        )

        # Update user record
        db_manager = get_database_manager()
        await db_manager.update_user_telegram_info(current_user["id"], None, False)

        return RedirectResponse(url="/dashboard", status_code=302)
    except Exception as e:
        logger.error(f"Error disconnecting user {current_user['id']}: {e}")
        raise HTTPException(status_code=500, detail="Disconnection failed")


@router.post("/delete-session")
async def telegram_delete_session(
    request: Request, current_user: dict = Depends(get_current_user)
):
    """Delete Telegram session files for the current user."""
    try:
        user_id = current_user["id"]
        username = current_user["username"]

        # Find and delete session files for this user
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

        # Disconnect any active Telegram client for this user
        try:
            telegram_manager = get_telegram_manager()
            if telegram_manager and user_id in telegram_manager.clients:
                client = telegram_manager.clients[user_id]
                if client.client and client.client.is_connected():
                    await client.client.disconnect()
                    logger.info(
                        f"Disconnected active Telegram client for user {user_id} ({username})"
                    )

                # Remove from manager
                del telegram_manager.clients[user_id]
                logger.info(
                    f"Removed client from manager for user {user_id} ({username})"
                )
        except Exception as e:
            logger.error(f"Error disconnecting client for user {user_id}: {e}")

        if deleted_files:
            message = f"Successfully deleted {len(deleted_files)} session file(s). You can now reconnect to Telegram."
            logger.info(
                f"Session cleanup completed for user {user_id} ({username}): {deleted_files}"
            )
        else:
            message = "No session files found to delete."
            logger.info(f"No session files found for user {user_id} ({username})")

        return RedirectResponse(
            url=f"/dashboard?message={message}&type=success", status_code=302
        )

    except Exception as e:
        logger.error(f"Error deleting session for user {current_user['id']}: {e}")
        return RedirectResponse(
            url=f"/dashboard?message=Failed to delete session: {str(e)}&type=error",
            status_code=302,
        )
