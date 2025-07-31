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

__all__ = [
    'DatabaseManager',
    'get_database_manager',
    'set_database_path',
    'BaseDatabaseManager',
    'UserManager',
    'EnergyManager',
    'ProfileManager', 
    'BadwordsManager',
    'SessionManager',
    'AuthManager',
    'AutocorrectManager'
]

# Compatibility functions for existing code
async def init_database_manager():
    """Initialize the database manager and create tables."""
    from .manager import get_database_manager, set_database_path
    import os
    
    database_path = os.path.join(os.getcwd(), "app.db")
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
