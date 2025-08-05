import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Request
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token security
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a new access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return {"id": int(user_id)}
    except JWTError:
        return None


async def get_current_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Get current user from token."""
    try:
        payload = verify_token(token)
        if not payload:
            return None

        user_id = payload.get("id")
        if not user_id:
            return None

        # Get user from database using the database manager
        from app.database.manager import get_database_manager

        db_manager = get_database_manager()
        user_data = await db_manager.users.get_user_by_id(int(user_id))

        if user_data:
            return {
                "id": user_data["id"],
                "username": user_data["username"],
                "is_admin": bool(user_data.get("is_admin", False)),
            }

        return None
    except Exception as e:
        logger.error(f"Error getting current user from token: {e}")
        return None


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Get current user from request (cookie or header)."""
    # Try to get token from cookie first
    token = request.cookies.get("access_token")

    # If no cookie, try Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_current_user_from_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_with_session_check(request: Request) -> Dict[str, Any]:
    """Get current user and check if they have active Telegram sessions."""
    user = await get_current_user(request)

    # Check if user has active Telegram session
    from app.database import get_database_manager

    db_manager = get_database_manager()
    has_active_session = await db_manager.has_active_telegram_session(user["id"])

    if has_active_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You have an active Telegram session. Disconnect your session to access dashboard settings.",
        )

    return user


async def get_current_admin_user(request: Request) -> Dict[str, Any]:
    """Get current user and verify they have admin privileges."""
    user = await get_current_user(request)

    # Check if user is admin
    from app.database import get_database_manager

    db_manager = get_database_manager()
    is_admin = await db_manager.is_admin(user["id"])

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Admin privileges required.",
        )

    user["is_admin"] = True
    return user
