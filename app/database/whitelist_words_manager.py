"""
Whitelist words database operations.
Words that are always allowed to be sent, even when power is 0 or sending would make power 0.
"""

import logging
from typing import Dict, Any, List
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class WhitelistWordsManager(BaseDatabaseManager):
    """Handles all whitelist words database operations."""

    async def get_user_whitelist_words(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all whitelist words for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT word, case_sensitive, created_at 
                       FROM user_whitelist_words WHERE user_id = ? 
                       ORDER BY word""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "word": row[0],
                        "case_sensitive": row[1],
                        "created_at": row[2],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error getting whitelist words for user {user_id}: {e}")
            return []

    @retry_db_operation()
    async def add_whitelist_word(
        self, user_id: int, word: str, case_sensitive: bool = False
    ) -> bool:
        """Add a whitelist word for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_whitelist_words 
                       (user_id, word, case_sensitive)
                       VALUES (?, ?, ?)""",
                    (user_id, word.strip(), case_sensitive),
                )
                await db.commit()
                logger.info(f"Added whitelist word '{word}' for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding whitelist word for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def remove_whitelist_word(self, user_id: int, word: str) -> bool:
        """Remove a whitelist word for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM user_whitelist_words WHERE user_id = ? AND word = ?",
                    (user_id, word.strip()),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing whitelist word for user {user_id}: {e}")
            return False

    async def is_message_whitelisted(self, user_id: int, message: str) -> bool:
        """
        Check if the entire message matches a whitelist word exactly.
        Whitelist words must match the whole message, not just part of it.

        Returns:
            bool: True if message exactly matches a whitelist word
        """
        try:
            whitelist_words = await self.get_user_whitelist_words(user_id)
            if not whitelist_words:
                return False

            message_stripped = message.strip()

            for word_info in whitelist_words:
                word = word_info["word"]
                case_sensitive = word_info["case_sensitive"]

                # Check for exact match
                if case_sensitive:
                    if message_stripped == word:
                        logger.info(
                            f"Message '{message}' matched whitelist word '{word}' (case sensitive) for user {user_id}"
                        )
                        return True
                else:
                    if message_stripped.lower() == word.lower():
                        logger.info(
                            f"Message '{message}' matched whitelist word '{word}' (case insensitive) for user {user_id}"
                        )
                        return True

            return False

        except Exception as e:
            logger.error(f"Error checking whitelist words for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def clear_all_whitelist_words(self, user_id: int) -> bool:
        """Clear all whitelist words for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    "DELETE FROM user_whitelist_words WHERE user_id = ?",
                    (user_id,),
                )
                await db.commit()
                logger.info(f"Cleared all whitelist words for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error clearing whitelist words for user {user_id}: {e}")
            return False
