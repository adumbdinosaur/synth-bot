"""
Custom redactions database operations.
Allows controllers to specify custom word replacements with penalties for specific users.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class CustomRedactionsManager(BaseDatabaseManager):
    """Handles all custom redactions database operations."""

    async def get_user_custom_redactions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all custom redactions for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT original_word, replacement_word, penalty, case_sensitive, created_at 
                       FROM user_custom_redactions WHERE user_id = ? 
                       ORDER BY LENGTH(original_word) DESC, original_word""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                redactions = []
                for row in rows:
                    # Convert created_at string to datetime object if it exists
                    created_at = None
                    if row[4]:
                        try:
                            created_at = datetime.fromisoformat(row[4])
                        except (ValueError, TypeError):
                            # If conversion fails, keep as string or set to None
                            created_at = row[4]

                    redactions.append(
                        {
                            "original_word": row[0],
                            "replacement_word": row[1],
                            "penalty": row[2],
                            "case_sensitive": row[3],
                            "created_at": created_at,
                        }
                    )
                return redactions
        except Exception as e:
            logger.error(f"Error getting custom redactions for user {user_id}: {e}")
            return []

    @retry_db_operation()
    async def add_custom_redaction(
        self,
        user_id: int,
        original_word: str,
        replacement_word: str,
        penalty: int = 5,
        case_sensitive: bool = False,
    ) -> bool:
        """Add a custom redaction for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_custom_redactions 
                       (user_id, original_word, replacement_word, penalty, case_sensitive)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        original_word.strip(),
                        replacement_word.strip(),
                        penalty,
                        case_sensitive,
                    ),
                )
                await db.commit()
                logger.info(
                    f"Added custom redaction '{original_word}' -> '{replacement_word}' for user {user_id}"
                )
                return True
        except Exception as e:
            logger.error(f"Error adding custom redaction for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def remove_custom_redaction(self, user_id: int, original_word: str) -> bool:
        """Remove a custom redaction for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM user_custom_redactions WHERE user_id = ? AND original_word = ?",
                    (user_id, original_word.strip()),
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing custom redaction for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def update_custom_redaction(
        self,
        user_id: int,
        original_word: str,
        replacement_word: str = None,
        penalty: int = None,
    ) -> bool:
        """Update a custom redaction for a user."""
        try:
            updates = []
            params = []

            if replacement_word is not None:
                updates.append("replacement_word = ?")
                params.append(replacement_word.strip())

            if penalty is not None:
                updates.append("penalty = ?")
                params.append(penalty)

            if not updates:
                return False

            params.extend([user_id, original_word.strip()])

            async with self.get_connection() as db:
                cursor = await db.execute(
                    f"""UPDATE user_custom_redactions SET {", ".join(updates)} 
                        WHERE user_id = ? AND original_word = ?""",
                    params,
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating custom redaction for user {user_id}: {e}")
            return False

    async def check_for_custom_redactions(
        self, user_id: int, message: str
    ) -> Tuple[bool, str, List[Dict[str, Any]], int]:
        """
        Check message for custom redactions and return processed message with penalty.

        Returns:
            Tuple of (has_redactions, processed_message, found_redactions_list, total_penalty)
        """
        try:
            custom_redactions = await self.get_user_custom_redactions(user_id)
            if not custom_redactions:
                return False, message, [], 0

            processed_message = message
            found_redactions = []
            total_penalty = 0

            for redaction in custom_redactions:
                original_word = redaction["original_word"]
                replacement_word = redaction["replacement_word"]
                penalty = redaction["penalty"]
                case_sensitive = redaction["case_sensitive"]

                # Create pattern for word matching
                import re

                if case_sensitive:
                    pattern = re.compile(r"\b" + re.escape(original_word) + r"\b")
                else:
                    pattern = re.compile(
                        r"\b" + re.escape(original_word) + r"\b", re.IGNORECASE
                    )

                # Find all matches
                matches = pattern.findall(processed_message)
                if matches:
                    # Replace the word
                    processed_message = pattern.sub(replacement_word, processed_message)

                    # Track the redaction
                    found_redactions.append(
                        {
                            "original_word": original_word,
                            "replacement_word": replacement_word,
                            "penalty": penalty,
                            "count": len(matches),
                        }
                    )

                    # Add penalty for each occurrence
                    total_penalty += penalty * len(matches)

            has_redactions = len(found_redactions) > 0
            return has_redactions, processed_message, found_redactions, total_penalty

        except Exception as e:
            logger.error(f"Error checking custom redactions for user {user_id}: {e}")
            return False, message, [], 0

    async def get_redaction_statistics(self, user_id: int) -> Dict[str, Any]:
        """Get statistics about custom redactions for a user."""
        try:
            custom_redactions = await self.get_user_custom_redactions(user_id)

            total_redactions = len(custom_redactions)
            total_penalty_potential = sum(
                redaction["penalty"] for redaction in custom_redactions
            )

            return {
                "total_redactions": total_redactions,
                "total_penalty_potential": total_penalty_potential,
                "redactions": custom_redactions,
            }
        except Exception as e:
            logger.error(f"Error getting redaction statistics for user {user_id}: {e}")
            return {
                "total_redactions": 0,
                "total_penalty_potential": 0,
                "redactions": [],
            }
