"""
Database module for the Telegram UserBot.

This module provides modular database operations organized by functionality.
"""

from .manager import DatabaseManager, get_database_manager, set_database_path
from .base import BaseDatabaseManager
from .user_manager import UserManager
from .energy_manager import EnergyManager
from .profile_manager import ProfileManager
from .badwords_manager import BadwordsManager
from .session_manager import SessionManager
from .auth_manager import AuthManager
from .autocorrect_manager import AutocorrectManager
from .chat_blacklist_manager import ChatBlacklistManager
from .chat_whitelist_manager import ChatWhitelistManager
from .chat_list_settings_manager import ChatListSettingsManager
from .whitelist_words_manager import WhitelistWordsManager

__all__ = [
    "DatabaseManager",
    "get_database_manager",
    "set_database_path",
    "BaseDatabaseManager",
    "UserManager",
    "EnergyManager",
    "ProfileManager",
    "BadwordsManager",
    "SessionManager",
    "AuthManager",
    "AutocorrectManager",
    "ChatBlacklistManager",
    "ChatWhitelistManager",
    "ChatListSettingsManager",
    "WhitelistWordsManager",
]


# Compatibility functions for existing code
async def init_database_manager():
    """Initialize the database manager and create tables."""
    from .manager import get_database_manager, set_database_path
    import os

    # Use DATABASE_URL environment variable if available, otherwise fall back to default
    database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # Extract the path from sqlite URL
    if database_url.startswith("sqlite:///"):
        database_path = database_url[10:]  # Remove 'sqlite:///' prefix
        # Convert relative path to absolute if needed
        if database_path.startswith("./"):
            database_path = os.path.join(os.getcwd(), database_path[2:])
    else:
        # Fallback to old behavior
        database_path = os.path.join(os.getcwd(), "app.db")

    # Ensure the directory exists
    os.makedirs(os.path.dirname(database_path), exist_ok=True)

    set_database_path(database_path)

    db_manager = get_database_manager()
    return await db_manager.initialize_all()


async def get_db_connection():
    """Get a database connection with proper locking - standalone function for compatibility."""
    from .manager import get_database_manager

    db_manager = get_database_manager()
    async with db_manager.get_connection() as db:
        yield db


async def get_db():
    """Get database connection for FastAPI dependency injection."""
    async with get_db_connection() as db:
        yield db


async def init_user_profile_protection(user_id: int):
    """Initialize default profile protection settings for a new user - standalone function."""
    from .manager import get_database_manager

    db_manager = get_database_manager()
    return await db_manager.init_user_profile_protection(user_id)
