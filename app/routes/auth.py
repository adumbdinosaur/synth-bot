"""Authentication routes for login, register, logout."""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import logging

from app.database import get_database_manager
from app.auth import (
    create_access_token,
    get_current_user,
    verify_password,
    get_password_hash,
    get_current_user_from_token,
)

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirect to dashboard if authenticated, otherwise show landing page."""
    # Check if user is already authenticated
    try:
        # Try to get the current user without raising exceptions
        token = request.cookies.get("access_token")
        if token:
            user = await get_current_user_from_token(token)
            if user:
                # User is authenticated, redirect to dashboard
                return RedirectResponse(url="/dashboard", status_code=302)
    except Exception:
        # If authentication fails, continue to show landing page
        pass

    # User is not authenticated, show login-focused landing page
    return templates.TemplateResponse("landing.html", {"request": request})


@router.get("/home", response_class=HTMLResponse)
async def home_authenticated(
    request: Request, current_user: dict = Depends(get_current_user)
):
    """Original home page, now only for authenticated users."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "user": current_user}
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    invite_code: str = Form(...),
):
    """Handle user registration."""
    try:
        db_manager = get_database_manager()

        # Validate invite code
        is_valid_code = await db_manager.validate_invite_code(invite_code)
        if not is_valid_code:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "Invalid or expired invite code"},
            )

        # Check if user already exists
        existing_user = await db_manager.get_user_by_username(username)
        if existing_user:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "Username already exists"},
            )

        # Use the invite code (increment usage count)
        await db_manager.use_invite_code(invite_code)

        # Create new user
        hashed_password = get_password_hash(password)
        user_id = await db_manager.create_user(username, hashed_password)

        # Initialize default energy costs for the new user
        await db_manager.init_user_energy_costs(user_id)

        # Initialize default profile protection settings for the new user
        from app.database import init_user_profile_protection

        await init_user_profile_protection(user_id)

        return RedirectResponse(url="/login", status_code=302)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Registration failed"}
        )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Handle user login."""
    try:
        logger.info(f"🔐 Login attempt for username: {username}")
        db_manager = get_database_manager()

        # Verify user credentials
        user_data = await db_manager.get_user_by_username(username)
        logger.info(f"🔍 User lookup result: {'Found' if user_data else 'Not found'}")

        if user_data:
            logger.info(
                f"🔍 Found user: {user_data['username']} (ID: {user_data['id']})"
            )
            password_valid = verify_password(password, user_data["hashed_password"])
            logger.info(
                f"🔑 Password verification: {'Valid' if password_valid else 'Invalid'}"
            )
        else:
            password_valid = False

        if not user_data or not password_valid:
            logger.warning(f"❌ Login failed for username: {username}")
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Invalid credentials"}
            )

        # Create access token
        access_token = create_access_token(data={"sub": str(user_data["id"])})
        logger.info(f"✅ Login successful for user: {username} (ID: {user_data['id']})")

        # Redirect to dashboard with token in cookie
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
        )
        logger.info("🍪 Setting access token cookie and redirecting to dashboard")
        return response
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Login failed"}
        )


@router.get("/logout")
async def logout_get():
    """Handle GET logout."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.post("/logout")
async def logout():
    """Handle POST logout."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response
