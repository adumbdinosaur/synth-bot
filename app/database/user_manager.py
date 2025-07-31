"""
User management database operations.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class UserManager(BaseDatabaseManager):
    """Handles all user-related database operations."""

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    @retry_db_operation()
    async def create_user(self, username: str, email: str, hashed_password: str) -> int:
        """Create a new user and return the user ID."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO users (username, email, hashed_password, energy, max_energy, energy_recharge_rate, last_energy_update) 
                   VALUES (?, ?, ?, 100, 100, 1, ?)""",
                (username, email, hashed_password, datetime.now().isoformat()),
            )
            await db.commit()
            return cursor.lastrowid

    @retry_db_operation()
    async def update_user_telegram_info(
        self, user_id: int, phone_number: str, connected: bool = True
    ):
        """Update user's Telegram connection info."""
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE users SET telegram_connected = ?, phone_number = ? WHERE id = ?",
                (connected, phone_number, user_id),
            )
            await db.commit()

    @retry_db_operation()
    async def create_admin_user(
        self, username: str, email: str, hashed_password: str
    ) -> int:
        """Create a new admin user and return the user ID."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO users (username, email, hashed_password, energy, max_energy, 
                   energy_recharge_rate, last_energy_update, is_admin) 
                   VALUES (?, ?, ?, 100, 100, 1, ?, TRUE)""",
                (username, email, hashed_password, datetime.now().isoformat()),
            )
            await db.commit()
            return cursor.lastrowid

    async def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT is_admin FROM users WHERE id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return bool(row[0]) if row else False
