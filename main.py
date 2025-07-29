import os
import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

from app.database_manager import init_database_manager, get_database_manager
from app.auth import (
    create_access_token,
    verify_token,
    get_current_user,
    verify_password,
    get_password_hash,
)
from app.models import User, TelegramMessage
from app.telegram_client import (
    initialize_telegram_manager,
    get_telegram_manager,
    recover_telegram_sessions,
)
from app.utils import is_authenticated
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
        from app.database import init_user_profile_protection

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
    type: str = None,
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
                if client.client is not None:
                    is_connected = client.client.is_connected()
                    is_auth = await client.is_fully_authenticated()
                    is_client_connected = is_connected and is_auth
            except Exception as e:
                logger.error(f"Error checking client status: {e}")

        # Get system statistics
        telegram_manager = get_telegram_manager()
        connected_users = telegram_manager.get_connected_users()
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
                "message_type": type or "info",
            },
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
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
    connected_users = telegram_manager.get_connected_users()
    total_clients = telegram_manager.get_client_count()

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
