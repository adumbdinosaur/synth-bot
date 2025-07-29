#!/usr/bin/env python3
"""
Minimal version of main.py to test the authentication issue without client recovery.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from dotenv import load_dotenv

from app.database import init_db, get_db
from app.auth import create_access_token, verify_password, get_current_user
from app.telegram_client import initialize_telegram_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
    await init_db()
    logger.info("Database initialized successfully")

    logger.info("🚀 Minimal app started")

    yield

    logger.info("🔚 Minimal app shutting down")


app = FastAPI(
    title="Telegram UserBot Web Interface (Minimal)",
    description="Minimal version for testing authentication",
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


# Setup templates
templates = Jinja2Templates(directory="templates")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Minimal server is running"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    try:
        # Verify user credentials
        cursor = await db.execute(
            "SELECT id, username, hashed_password FROM users WHERE username = ?",
            (username,),
        )
        user_data = await cursor.fetchone()

        if not user_data or not verify_password(password, user_data[2]):
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Invalid credentials"}
            )

        # Create access token
        access_token = create_access_token(data={"sub": str(user_data[0])})

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
        logger.error(f"Login error: {e}")
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Login failed"}
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": current_user,
                "telegram_connected": False,
                "phone_number": None,
                "client_connected": False,
                "total_active_users": 0,
                "total_clients": 0,
                "user_in_connected": False,
                "session_files_count": 0,
                "has_session_files": False,
                "energy_level": 100,  # Default energy
                "message": "Welcome to the minimal test dashboard!",
                "message_type": "info",
            },
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
