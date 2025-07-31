"""Application configuration and startup logic."""

import os
import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from dotenv import load_dotenv

from app.database import init_database_manager, get_database_manager
from app.auth import get_password_hash
from app.telegram_client import (
    initialize_telegram_manager,
    get_telegram_manager,
    recover_telegram_sessions,
)

logger = logging.getLogger(__name__)


def configure_logging():
    """Configure application logging."""
    if os.path.exists("logging.conf"):
        logging.config.fileConfig("logging.conf")
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


async def initialize_telegram():
    """Initialize Telegram manager with API credentials."""
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


async def initialize_database():
    """Initialize database connection and tables."""
    logger.info("Initializing database...")
    await init_database_manager()
    logger.info("Database initialized successfully")


async def create_default_admin():
    """Create default admin account if none exists."""
    logger.info("Checking for admin accounts...")
    try:
        db_manager = get_database_manager()
        users = await db_manager.get_all_users()
        admin_users = [user for user in users if user.get("is_admin")]

        if not admin_users:
            logger.info("No admin accounts found. Creating default admin account...")

            # Check if username 'admin' already exists as regular user
            existing_admin_user = await db_manager.get_user_by_username("admin")
            if existing_admin_user:
                # Promote existing 'admin' user to admin status
                await db_manager.toggle_admin_status(existing_admin_user["id"])
                logger.info("✅ Promoted existing 'admin' user to admin status")
            else:
                # Create new admin user
                admin_password = "Vru3s^C&DUdSUea5NbJK"
                admin_email = "admin@localhost"
                hashed_password = get_password_hash(admin_password)

                admin_user_id = await db_manager.create_admin_user(
                    username="admin", email=admin_email, hashed_password=hashed_password
                )

                # Initialize default settings for admin user
                await db_manager.init_user_energy_costs(admin_user_id)
                from app.database import init_user_profile_protection

                await init_user_profile_protection(admin_user_id)

                logger.info(
                    f"✅ Created default admin account: admin (ID: {admin_user_id})"
                )
                logger.info(
                    "🔑 Admin credentials - Username: admin, Password: Vru3s^C&DUdSUea5NbJK"
                )
        else:
            logger.info(f"✅ Found {len(admin_users)} existing admin account(s)")

    except Exception as e:
        logger.error(f"❌ Error setting up admin account: {e}")
        import traceback

        traceback.print_exc()


async def start_client_recovery():
    """Start background client recovery task."""

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


async def cleanup_telegram():
    """Cleanup telegram clients during shutdown."""
    logger.info("Cleaning up Telegram clients...")
    try:
        telegram_manager = get_telegram_manager()
        await telegram_manager.disconnect_all()
        logger.info("All Telegram clients disconnected successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


async def cleanup_database():
    """Run database cleanup operations."""
    logger.info("Running database cleanup operations...")
    try:
        db_manager = get_database_manager()

        # Clean up duplicate autocorrect settings
        deleted_count = await db_manager.autocorrect.cleanup_duplicate_settings()

        if deleted_count > 0:
            logger.info(f"🗑️ Removed {deleted_count} duplicate autocorrect entries")

        logger.info("✅ Database cleanup completed")

    except Exception as e:
        logger.error(f"❌ Error during database cleanup: {e}")
        # Don't fail startup for cleanup errors, just log them
        import traceback

        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await initialize_telegram()
    await initialize_database()
    await cleanup_database()  # Run database cleanup after initialization
    await create_default_admin()

    # Log startup message
    logger.info("🚀 Telegram UserBot application started")
    telegram_manager = get_telegram_manager()
    if telegram_manager:
        logger.info(
            f"📊 Telegram manager ready for {telegram_manager.get_client_count()} clients"
        )
    else:
        logger.warning("⚠️ Telegram manager not initialized properly")

    # Start client recovery in background
    await start_client_recovery()

    yield

    # Cleanup
    await cleanup_telegram()
    logger.info("Application shutdown complete")


def create_exception_handlers(app: FastAPI, templates: Jinja2Templates):
    """Create and configure exception handlers."""

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
        elif exc.status_code == 403:
            # Check if this is a session-related restriction
            if "active Telegram session" in str(exc.detail):
                # For API requests, return JSON
                if request.url.path.startswith("/api/"):
                    return JSONResponse(status_code=403, content={"detail": exc.detail})
                # For web requests, show blocked page
                return templates.TemplateResponse(
                    "dashboard_blocked.html",
                    {"request": request, "message": exc.detail},
                )

        # For other HTTP exceptions, let FastAPI handle them normally
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def mount_static_files(app: FastAPI):
    """Mount static file directories."""
    # Mount more specific routes first
    app.mount(
        "/static/profile_photos",
        StaticFiles(directory="data/profile_photos"),
        name="profile_photos",
    )
    app.mount("/static", StaticFiles(directory="static"), name="static")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Load environment variables
    load_dotenv()

    # Configure logging
    configure_logging()

    # Create FastAPI app
    app = FastAPI(
        title="Telegram UserBot Web Interface",
        description="Secure web application for Telegram userbot management",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Mount static files
    mount_static_files(app)

    # Create templates instance
    templates = Jinja2Templates(directory="templates")

    # Create exception handlers
    create_exception_handlers(app, templates)

    return app
