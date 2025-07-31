"""
Chat blacklist database operations.
"""

import logging
from typing import Dict, Any, List
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class ChatBlacklistManager(BaseDatabaseManager):
    """Handles all chat blacklist database operations for users with locked profiles."""

    async def get_user_blacklisted_chats(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all blacklisted chats for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT chat_id, chat_title, chat_type, created_at 
                       FROM user_chat_blacklist WHERE user_id = ? 
                       ORDER BY chat_title, chat_id""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "chat_id": row[0],
                        "chat_title": row[1] or f"Chat {row[0]}",
                        "chat_type": row[2] or "unknown",
                        "created_at": row[3],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error getting blacklisted chats for user {user_id}: {e}")
            return []

    @retry_db_operation()
    async def add_blacklisted_chat(
        self, user_id: int, chat_id: int, chat_title: str = None, chat_type: str = None
    ) -> bool:
        """Add a chat to the blacklist for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_chat_blacklist 
                       (user_id, chat_id, chat_title, chat_type)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, chat_id, chat_title, chat_type),
                )
                await db.commit()
                logger.info(f"Added chat {chat_id} to blacklist for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding blacklisted chat for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def remove_blacklisted_chat(self, user_id: int, chat_id: int) -> bool:
        """Remove a chat from the blacklist for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM user_chat_blacklist WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing blacklisted chat for user {user_id}: {e}")
            return False

    async def is_chat_blacklisted(self, user_id: int, chat_id: int) -> bool:
        """Check if a chat is blacklisted for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM user_chat_blacklist WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id),
                )
                row = await cursor.fetchone()
                return row is not None
        except Exception as e:
            logger.error(f"Error checking if chat is blacklisted for user {user_id}: {e}")
            return False

    async def update_chat_info(
        self, user_id: int, chat_id: int, chat_title: str = None, chat_type: str = None
    ) -> bool:
        """Update chat information for a blacklisted chat."""
        try:
            async with self.get_connection() as db:
                # Only update if the chat exists in blacklist
                cursor = await db.execute(
                    """UPDATE user_chat_blacklist 
                       SET chat_title = COALESCE(?, chat_title),
                           chat_type = COALESCE(?, chat_type)
                       WHERE user_id = ? AND chat_id = ?""",
                    (chat_title, chat_type, user_id, chat_id),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating chat info for user {user_id}: {e}")
            return False
