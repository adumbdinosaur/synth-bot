"""
Chat list settings database operations.
"""

import logging
from datetime import datetime
from typing import Dict, Any
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class ChatListSettingsManager(BaseDatabaseManager):
    """Handles chat list settings (blacklist/whitelist mode) for users with locked profiles."""

    async def get_user_chat_list_mode(self, user_id: int) -> str:
        """Get the chat list mode for a user (blacklist or whitelist). Defaults to blacklist."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT list_mode FROM user_chat_list_settings WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                return row[0] if row else "blacklist"
        except Exception as e:
            logger.error(f"Error getting chat list mode for user {user_id}: {e}")
            return "blacklist"

    @retry_db_operation()
    async def set_user_chat_list_mode(self, user_id: int, list_mode: str) -> bool:
        """Set the chat list mode for a user (blacklist or whitelist)."""
        if list_mode not in ["blacklist", "whitelist"]:
            logger.error(f"Invalid list mode: {list_mode}")
            return False
            
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_chat_list_settings 
                       (user_id, list_mode, updated_at)
                       VALUES (?, ?, ?)""",
                    (user_id, list_mode, datetime.now().isoformat()),
                )
                await db.commit()
                logger.info(f"Set chat list mode to {list_mode} for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error setting chat list mode for user {user_id}: {e}")
            return False

    async def get_user_chat_list_settings(self, user_id: int) -> Dict[str, Any]:
        """Get all chat list settings for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT * FROM user_chat_list_settings WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                else:
                    # Return default settings
                    return {
                        "user_id": user_id,
                        "list_mode": "blacklist",
                        "created_at": None,
                        "updated_at": None,
                    }
        except Exception as e:
            logger.error(f"Error getting chat list settings for user {user_id}: {e}")
            return {
                "user_id": user_id,
                "list_mode": "blacklist",
                "created_at": None,
                "updated_at": None,
            }

    @retry_db_operation()
    async def toggle_user_chat_list_mode(self, user_id: int) -> str:
        """Toggle between blacklist and whitelist mode for a user. Returns the new mode."""
        try:
            current_mode = await self.get_user_chat_list_mode(user_id)
            new_mode = "whitelist" if current_mode == "blacklist" else "blacklist"
            
            if await self.set_user_chat_list_mode(user_id, new_mode):
                return new_mode
            else:
                return current_mode
        except Exception as e:
            logger.error(f"Error toggling chat list mode for user {user_id}: {e}")
            return "blacklist"
