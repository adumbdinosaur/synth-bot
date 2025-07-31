"""
Badwords filtering database operations.
"""

import logging
import re
from typing import Dict, Any, List, Tuple
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class BadwordsManager(BaseDatabaseManager):
    """Handles all badwords filtering database operations."""

    async def get_user_badwords(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all badwords for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT word, penalty, case_sensitive, created_at 
                       FROM user_badwords WHERE user_id = ? 
                       ORDER BY word""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "word": row[0],
                        "penalty": row[1],
                        "case_sensitive": row[2],
                        "created_at": row[3],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error getting badwords for user {user_id}: {e}")
            return []

    @retry_db_operation()
    async def add_badword(
        self, user_id: int, word: str, penalty: int = 5, case_sensitive: bool = False
    ) -> bool:
        """Add a badword for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_badwords 
                       (user_id, word, penalty, case_sensitive)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, word.strip(), penalty, case_sensitive),
                )
                await db.commit()
                logger.info(f"Added badword '{word}' for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding badword for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def remove_badword(self, user_id: int, word: str) -> bool:
        """Remove a badword for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM user_badwords WHERE user_id = ? AND word = ?",
                    (user_id, word.strip()),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing badword for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def update_badword_penalty(
        self, user_id: int, word: str, penalty: int
    ) -> bool:
        """Update the penalty for a specific badword."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """UPDATE user_badwords SET penalty = ? 
                       WHERE user_id = ? AND word = ?""",
                    (penalty, user_id, word.strip()),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating badword penalty for user {user_id}: {e}")
            return False

    async def check_for_badwords(
        self, user_id: int, message: str
    ) -> Tuple[bool, List[Dict[str, Any]], int]:
        """
        Check message for badwords and return found badwords with total penalty.

        Returns:
            Tuple of (has_badwords, found_badwords_list, total_penalty)
        """
        try:
            badwords = await self.get_user_badwords(user_id)
            if not badwords:
                return False, [], 0

            found_badwords = []
            total_penalty = 0

            for badword_info in badwords:
                word = badword_info["word"]
                penalty = badword_info["penalty"]
                case_sensitive = badword_info["case_sensitive"]

                # Create regex pattern for whole word matching
                if case_sensitive:
                    pattern = r"\b" + re.escape(word) + r"\b"
                    matches = re.findall(pattern, message)
                else:
                    pattern = r"\b" + re.escape(word) + r"\b"
                    matches = re.findall(pattern, message, re.IGNORECASE)

                if matches:
                    count = len(matches)
                    found_badwords.append(
                        {
                            "word": word,
                            "penalty": penalty,
                            "count": count,
                            "case_sensitive": case_sensitive,
                        }
                    )
                    total_penalty += penalty * count

            return len(found_badwords) > 0, found_badwords, total_penalty

        except Exception as e:
            logger.error(f"Error checking badwords for user {user_id}: {e}")
            return False, [], 0

    async def filter_badwords_from_message(
        self, user_id: int, message: str
    ) -> Dict[str, Any]:
        """
        Filter badwords from message and return filtered message with details.

        Returns:
            Dict with keys: filtered_message, found_badwords, total_penalty
        """
        try:
            has_badwords, found_badwords, total_penalty = await self.check_for_badwords(
                user_id, message
            )

            if not has_badwords:
                return {
                    "filtered_message": message,
                    "found_badwords": [],
                    "total_penalty": 0,
                }

            filtered_message = message
            badwords = await self.get_user_badwords(user_id)

            # Replace badwords with <redacted>
            for badword_info in badwords:
                word = badword_info["word"]
                case_sensitive = badword_info["case_sensitive"]

                if case_sensitive:
                    pattern = r"\b" + re.escape(word) + r"\b"
                    filtered_message = re.sub(pattern, "<redacted>", filtered_message)
                else:
                    pattern = r"\b" + re.escape(word) + r"\b"
                    filtered_message = re.sub(
                        pattern, "<redacted>", filtered_message, flags=re.IGNORECASE
                    )

            return {
                "filtered_message": filtered_message,
                "found_badwords": found_badwords,
                "total_penalty": total_penalty,
            }

        except Exception as e:
            logger.error(f"Error filtering badwords for user {user_id}: {e}")
            return {
                "filtered_message": message,
                "found_badwords": [],
                "total_penalty": 0,
            }
