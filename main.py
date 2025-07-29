import os
import asyncio
import logging
import logging.config
import time
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import (
    FastAPI,
    Request,
    Depends,
    HTTPException,
    Form,
    File,
    UploadFile,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from dotenv import load_dotenv

from app.database_manager import init_database_manager, get_database_manager
from app.auth import (
    create_access_token,
    get_current_user,
    verify_password,
    get_password_hash,
)
from app.telegram_client import (
    initialize_telegram_manager,
    get_telegram_manager,
    recover_telegram_sessions,
)
from app.energy_simple import EnergyManager

# Load environment variables
load_dotenv()

# Configure logging
if os.path.exists("logging.conf"):
    logging.config.fileConfig("logging.conf")
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Telegram manager
    logger.info("Initializing Telegram manager...")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        logger.error(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables are required"
        )
        raise RuntimeError("Missing Telegram API credentials")

    initialize_telegram_manager(int(api_id), api_hash)
    logger.info("Telegram manager initialized successfully")

    # Initialize database
    logger.info("Initializing database...")
    await init_database_manager()
    logger.info("Database initialized successfully")

    # Log startup message
    logger.info("🚀 Telegram UserBot application started")
    telegram_manager = get_telegram_manager()
    if telegram_manager:
        logger.info(
            f"📊 Telegram manager ready for {telegram_manager.get_client_count()} clients"
        )
    else:
        logger.warning("⚠️ Telegram manager not initialized properly")

    # Start client recovery in background (non-blocking)
    async def recover_clients_background():
        """Recover existing Telegram clients from session files in background."""
        await asyncio.sleep(2)  # Small delay to ensure server is fully started
        logger.info("🔄 Starting background client recovery...")
        try:
            await recover_telegram_sessions()
            logger.info("✅ Background client recovery completed successfully")
        except Exception as e:
            logger.error(f"❌ Error during background client recovery: {e}")
            import traceback

            traceback.print_exc()

    # Start recovery task in background
    asyncio.create_task(recover_clients_background())

    yield

    # Cleanup telegram clients
    logger.info("Cleaning up Telegram clients...")
    try:
        telegram_manager = get_telegram_manager()
        await telegram_manager.disconnect_all()
        logger.info("All Telegram clients disconnected successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

    logger.info("Application shutdown complete")


app = FastAPI(
    title="Telegram UserBot Web Interface",
    description="Secure web application for Telegram userbot management",
    version="1.0.0",
    lifespan=lifespan,
)


# Exception handler for authentication errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        # For API requests, return JSON
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=401, content={"detail": "Not authenticated"}
            )
        # For web requests, redirect to login
        return RedirectResponse(url="/login", status_code=302)

    # For other HTTP exceptions, let FastAPI handle them normally
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount(
    "/static/profile_photos",
    StaticFiles(directory="data/profile_photos"),
    name="profile_photos",
)
templates = Jinja2Templates(directory="templates")


@app.get("/health")
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


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        db_manager = get_database_manager()

        # Check if user already exists
        existing_user = await db_manager.get_user_by_username(username)
        if existing_user:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "Username or email already exists"},
            )

        # Create new user
        hashed_password = get_password_hash(password)
        user_id = await db_manager.create_user(username, email, hashed_password)

        # Initialize default energy costs for the new user
        await db_manager.init_user_energy_costs(user_id)

        # Initialize default profile protection settings for the new user
        from app.database_manager import init_user_profile_protection

        await init_user_profile_protection(user_id)

        return RedirectResponse(url="/login", status_code=302)
    except Exception as e:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Registration failed"}
        )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    try:
        db_manager = get_database_manager()

        # Verify user credentials
        user_data = await db_manager.get_user_by_username(username)

        if not user_data or not verify_password(password, user_data["hashed_password"]):
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Invalid credentials"}
            )

        # Create access token
        access_token = create_access_token(data={"sub": str(user_data["id"])})

        # Redirect to dashboard with token in cookie
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
        )
        return response
    except Exception as e:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Login failed"}
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
    message: str = None,
    message_type: str = None,
):
    try:
        db_manager = get_database_manager()

        # Get user's Telegram connection status
        user_data = await db_manager.get_user_by_id(current_user["id"])

        # Get client connection status from manager
        telegram_manager = get_telegram_manager()
        client = await telegram_manager.get_client(current_user["id"])

        is_client_connected = False
        if client is not None:
            try:
                is_connected = client.is_connected  # Property, not method
                is_auth = await client.is_fully_authenticated()
                is_client_connected = is_connected and is_auth
            except Exception as e:
                logger.error(f"Error checking client status: {e}")

        # Get system statistics
        telegram_manager = get_telegram_manager()
        connected_users = await telegram_manager.get_connected_users()
        total_active_clients = telegram_manager.get_client_count()

        # Check for session files for this user
        user_id = current_user["id"]
        session_files = []
        if os.path.exists("sessions"):
            for filename in os.listdir("sessions"):
                if filename.startswith(f"user_{user_id}_") and filename.endswith(
                    ".session"
                ):
                    session_files.append(filename)

        # Get user's energy level
        energy_manager = EnergyManager()
        energy_info = await energy_manager.get_user_energy(user_id)
        energy_level = energy_info["energy"]

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
                "user_in_connected": current_user["id"] in connected_users,
                "session_files_count": len(session_files),
                "has_session_files": len(session_files) > 0,
                "energy_level": energy_level,
                "message": message,
                "message_type": message_type or "info",
            },
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        import traceback

        traceback.print_exc()
        raise


@app.get("/telegram/connect", response_class=HTMLResponse)
async def telegram_connect_page(
    request: Request, current_user: dict = Depends(get_current_user), error: str = None
):
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


@app.post("/telegram/connect")
async def telegram_connect(
    request: Request,
    phone_number: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
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


@app.post("/telegram/verify")
async def telegram_verify(
    request: Request,
    code: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
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


@app.post("/telegram/verify-2fa")
async def telegram_verify_2fa(
    request: Request,
    password: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
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


@app.post("/telegram/disconnect")
async def telegram_disconnect(current_user: dict = Depends(get_current_user)):
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


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


@app.get("/api/stats")
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


@app.post("/telegram/delete-session")
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


@app.get("/energy-settings", response_class=HTMLResponse)
async def energy_settings_page(
    request: Request, current_user: dict = Depends(get_current_user)
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


@app.post("/energy-settings")
async def update_energy_settings(
    request: Request,
    current_user: dict = Depends(get_current_user),
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


@app.get("/profile-protection", response_class=HTMLResponse)
async def profile_protection_page(
    request: Request, current_user: dict = Depends(get_current_user)
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


@app.post("/profile-protection")
async def update_profile_protection_settings(
    request: Request,
    current_user: dict = Depends(get_current_user),
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


@app.get("/badwords", response_class=HTMLResponse)
async def badwords_page(
    request: Request, current_user: dict = Depends(get_current_user)
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


@app.post("/badwords/add")
async def add_badword(
    request: Request,
    word: str = Form(...),
    penalty: int = Form(5),
    case_sensitive: bool = Form(False),
    current_user: dict = Depends(get_current_user),
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


@app.post("/badwords/remove")
async def remove_badword(
    request: Request,
    word: str = Form(...),
    current_user: dict = Depends(get_current_user),
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


@app.post("/badwords/update")
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


# Public Dashboard Routes
@app.get("/public", response_class=HTMLResponse)
async def public_dashboard(request: Request):
    """Public dashboard showing users who have enabled public control."""
    try:
        db_manager = get_database_manager()
        public_users = await db_manager.get_public_users()

        return templates.TemplateResponse(
            "public_dashboard.html",
            {
                "request": request,
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
                "users": [],
                "error": "Failed to load public dashboard",
            },
        )


@app.get("/public/sessions", response_class=HTMLResponse)
async def public_sessions_dashboard(request: Request):
    """Public dashboard showing all active Telegram sessions."""
    try:
        db_manager = get_database_manager()

        # Get all active sessions from database
        active_sessions = await db_manager.get_all_active_sessions()

        # Get connection status from telegram manager
        telegram_manager = get_telegram_manager()
        connected_users_info = await telegram_manager.get_connected_users()
        connected_user_ids = {user["user_id"] for user in connected_users_info}

        # Enhance session data with real-time connection status
        for session in active_sessions:
            session["is_connected"] = session["user_id"] in connected_user_ids

        return templates.TemplateResponse(
            "public_sessions_dashboard.html",
            {
                "request": request,
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
                "sessions": [],
                "total_sessions": 0,
                "connected_sessions": 0,
                "error": "Failed to load public sessions dashboard",
            },
        )


@app.get("/public/sessions/{user_id}", response_class=HTMLResponse)
async def public_session_info(request: Request, user_id: int):
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
            if client_instance and client_instance.profile_manager:
                current_profile = (
                    await client_instance.profile_manager.get_current_profile()
                )
                original_profile = client_instance.profile_manager.original_profile
                current_profile_photo_url = (
                    client_instance.profile_manager.get_profile_photo_url()
                )
                original_profile_photo_url = (
                    client_instance.profile_manager.get_original_profile_photo_url()
                )

        # Calculate current energy with recharge
        current_energy = user["energy"] if user["energy"] is not None else 100
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
        current_energy = min(100, current_energy + energy_to_add)

        session_info = {
            "user_id": user["id"],
            "username": user["username"],
            "telegram_connected": bool(user["telegram_connected"]),
            "energy": current_energy,
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
                "session": session_info,
                "energy_costs": energy_costs,
                "badwords": badwords,
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


@app.post("/public/sessions/{user_id}/energy-costs")
async def update_session_energy_costs(
    request: Request,
    user_id: int,
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


@app.post("/public/sessions/{user_id}/recharge-rate")
async def update_session_recharge_rate(
    request: Request,
    user_id: int,
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


@app.post("/public/sessions/{user_id}/profile/update")
async def update_user_profile(
    request: Request,
    user_id: int,
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
        if not client_instance or not client_instance.profile_manager:
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
            import os

            # Create temp directory if it doesn't exist
            temp_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp"
            )
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
        success = await client_instance.profile_manager.update_profile(
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
        save_success = await client_instance.profile_manager.save_current_as_original()
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


@app.post("/public/sessions/{user_id}/profile/revert-cost")
async def update_profile_revert_cost(
    request: Request, user_id: int, revert_cost: int = Form(...)
):
    """Update the energy cost for reverting profile changes."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate cost (0-100 energy)
        if not (0 <= revert_cost <= 100):
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Revert cost must be between 0 and 100 energy",
                status_code=303,
            )

        # Update the revert cost
        success = await db_manager.set_profile_revert_cost(user_id, revert_cost)

        if success:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Profile revert cost updated to {revert_cost} energy",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to update revert cost",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile revert cost for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update revert cost",
            status_code=303,
        )


@app.post("/public/energy/{user_id}")
async def public_set_energy(
    request: Request,
    user_id: int,
    energy: int = Form(...),
):
    """Allow public visitors to set energy for users who have enabled it."""
    try:
        db_manager = get_database_manager()
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")

        # Check if public access is enabled for this user
        access_settings = await db_manager.get_public_access_settings(user_id)
        if (
            not access_settings
            or not access_settings.get("public_control_enabled")
            or not access_settings.get("allow_energy_changes")
        ):
            raise HTTPException(
                status_code=403, detail="Energy changes not allowed for this user"
            )

        # Validate energy value
        if not (0 <= energy <= 100):
            raise HTTPException(
                status_code=400, detail="Energy must be between 0 and 100"
            )

        # Set the energy
        await db_manager.set_user_energy(user_id, energy)

        # Log the action
        await db_manager.log_public_action(
            user_id, "energy_change", f"Energy set to {energy}", client_ip, user_agent
        )

        return RedirectResponse(url="/public?success=energy_updated", status_code=303)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting energy for user {user_id}: {e}")
        return RedirectResponse(url="/public?error=energy_failed", status_code=303)


@app.post("/public/profile/{user_id}")
async def public_trigger_profile_change(
    request: Request,
    user_id: int,
):
    """Trigger a profile change for users who have enabled public profile control."""
    try:
        db_manager = get_database_manager()
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")

        # Check if public access is enabled for this user
        access_settings = await db_manager.get_public_access_settings(user_id)
        if (
            not access_settings
            or not access_settings.get("public_control_enabled")
            or not access_settings.get("allow_profile_changes")
        ):
            raise HTTPException(
                status_code=403, detail="Profile changes not allowed for this user"
            )

        # Get user info
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if user is connected to Telegram
        if not user["telegram_connected"]:
            raise HTTPException(
                status_code=400, detail="User is not connected to Telegram"
            )

        # Get telegram manager and trigger profile change
        telegram_manager = get_telegram_manager()

        # Trigger the profile change
        success = await telegram_manager.trigger_profile_change(user_id)

        if success:
            # Log the action
            await db_manager.log_public_action(
                user_id,
                "profile_change",
                "Profile change triggered",
                client_ip,
                user_agent,
            )
            return RedirectResponse(
                url="/public?success=profile_changed", status_code=303
            )
        else:
            return RedirectResponse(url="/public?error=profile_failed", status_code=303)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering profile change for user {user_id}: {e}")
        return RedirectResponse(url="/public?error=profile_failed", status_code=303)


@app.post("/public/profile/{user_id}/set")
async def public_set_profile(
    request: Request,
    user_id: int,
    first_name: str = Form(None),
    last_name: str = Form(None),
    bio: str = Form(None),
    photo_url: str = Form(None),
):
    """Set profile data for users who have enabled public profile control."""
    try:
        db_manager = get_database_manager()
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")

        # Check if public access is enabled for this user
        access_settings = await db_manager.get_public_access_settings(user_id)
        if (
            not access_settings
            or not access_settings.get("public_control_enabled")
            or not access_settings.get("allow_profile_changes")
        ):
            raise HTTPException(
                status_code=403, detail="Profile changes not allowed for this user"
            )

        # Get user info
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if user is connected to Telegram
        if not user["telegram_connected"]:
            raise HTTPException(
                status_code=400, detail="User is not connected to Telegram"
            )

        # Validate at least one field is provided
        if not any([first_name, last_name, bio, photo_url]):
            raise HTTPException(
                status_code=400, detail="At least one profile field must be provided"
            )

        # Get telegram manager and update profile
        telegram_manager = get_telegram_manager()

        # Build profile data
        profile_data = {}
        if first_name:
            profile_data["first_name"] = first_name.strip()
        if last_name:
            profile_data["last_name"] = last_name.strip()
        if bio:
            profile_data["bio"] = bio.strip()
        if photo_url:
            profile_data["photo_url"] = photo_url.strip()

        # Set the profile
        success = await telegram_manager.set_profile(user_id, profile_data)

        if success:
            # Log the action
            changes = ", ".join([f"{k}: {v}" for k, v in profile_data.items()])
            await db_manager.log_public_action(
                user_id,
                "profile_set",
                f"Profile updated: {changes}",
                client_ip,
                user_agent,
            )
            return RedirectResponse(
                url="/public?success=profile_updated", status_code=303
            )
        else:
            return RedirectResponse(url="/public?error=profile_failed", status_code=303)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting profile for user {user_id}: {e}")
        return RedirectResponse(url="/public?error=profile_failed", status_code=303)


@app.get("/public/profile/{user_id}/form", response_class=HTMLResponse)
async def public_profile_form(request: Request, user_id: int):
    """Show profile editing form for public users."""
    try:
        db_manager = get_database_manager()

        # Check if public access is enabled for this user
        access_settings = await db_manager.get_public_access_settings(user_id)
        if (
            not access_settings
            or not access_settings.get("public_control_enabled")
            or not access_settings.get("allow_profile_changes")
        ):
            raise HTTPException(
                status_code=403, detail="Profile changes not allowed for this user"
            )

        # Get user info
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get current profile data from telegram
        telegram_manager = get_telegram_manager()
        current_profile = await telegram_manager.get_profile(user_id)

        return templates.TemplateResponse(
            "public_profile_form.html",
            {
                "request": request,
                "user": user,
                "current_profile": current_profile or {},
                "access_settings": access_settings,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading profile form for user {user_id}: {e}")
        return RedirectResponse(
            url="/public?error=profile_form_failed", status_code=303
        )


@app.post("/public/sessions/{user_id}/badwords/add")
async def public_add_badword(
    request: Request,
    user_id: int,
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


@app.post("/public/sessions/{user_id}/badwords/remove")
async def public_remove_badword(
    request: Request,
    user_id: int,
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
                url=f"/public/sessions/{user_id}?error=Badword not found or failed to remove",
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


@app.post("/public/sessions/{user_id}/badwords/update")
async def public_update_badword(
    request: Request,
    user_id: int,
    word: str = Form(...),
    penalty: int = Form(...),
):
    """Update badword penalty for a user via public dashboard."""
    try:
        db_manager = get_database_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate penalty
        if not (1 <= penalty <= 100):
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Penalty must be between 1 and 100",
                status_code=303,
            )

        # Update the badword penalty
        success = await db_manager.update_badword_penalty(user_id, word, penalty)

        if success:
            logger.info(
                f"Updated badword '{word}' penalty to {penalty} for user {user_id}"
            )
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?success=Badword '{word}' penalty updated to {penalty}",
                status_code=303,
            )
        else:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Badword not found or failed to update",
                status_code=303,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating badword for user {user_id}: {e}")
        return RedirectResponse(
            url=f"/public/sessions/{user_id}?error=Failed to update badword",
            status_code=303,
        )


@app.post("/public/sessions/{user_id}/profile/update")
async def update_user_profile(
    request: Request,
    user_id: int,
    first_name: str = Form(None),
    last_name: str = Form(None),
    bio: str = Form(None),
    profile_photo: str = Form(None),  # For now, just handle text fields
    save_as_new_state: bool = Form(False),
):
    """Update user profile via ProfileManager - costs no energy."""
    try:
        db_manager = get_database_manager()
        telegram_manager = get_telegram_manager()

        # Verify user exists
        user = await db_manager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get the user's telegram client
        client_instance = telegram_manager.clients.get(user_id)
        if not client_instance or not client_instance.profile_manager:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=User not connected or profile manager not available",
                status_code=303,
            )

        # Update the profile using ProfileManager
        success = await client_instance.profile_manager.update_profile(
            first_name=first_name if first_name else None,
            last_name=last_name if last_name else None,
            bio=bio if bio else None,
            profile_photo_file=None,  # TODO: Handle file uploads later
        )

        if not success:
            return RedirectResponse(
                url=f"/public/sessions/{user_id}?error=Failed to update profile",
                status_code=303,
            )

        # If requested, save the current state as the new original/saved state
        if save_as_new_state:
            save_success = (
                await client_instance.profile_manager.save_current_as_original()
            )
            if save_success:
                logger.info(f"Saved new profile state for user {user_id}")
                message = "Profile updated and saved as new state"
            else:
                logger.warning(
                    f"Profile updated but failed to save new state for user {user_id}"
                )
                message = "Profile updated but failed to save as new state"
        else:
            message = "Profile updated successfully"

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
