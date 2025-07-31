"""
Autocorrect system database operations.
"""

import logging
from datetime import datetime
from typing import Dict, Any
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class AutocorrectManager(BaseDatabaseManager):
    """Handles all autocorrect system database operations."""

    async def get_autocorrect_settings(self, user_id: int) -> Dict[str, Any]:
        """Get autocorrect settings for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM user_autocorrect_settings WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            else:
                # Return default settings if none exist
                return {
                    "user_id": user_id,
                    "enabled": False,
                    "penalty_per_correction": 5,
                }

    @retry_db_operation()
    async def update_autocorrect_settings(
        self, user_id: int, enabled: bool, penalty_per_correction: int
    ):
        """Update autocorrect settings for a user."""
        async with self.get_connection() as db:
            # Check if user already has settings
            cursor = await db.execute(
                "SELECT id FROM user_autocorrect_settings WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
            existing = await cursor.fetchone()

            if existing:
                # Update existing record
                await db.execute(
                    """UPDATE user_autocorrect_settings 
                       SET enabled = ?, penalty_per_correction = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        enabled,
                        penalty_per_correction,
                        datetime.now().isoformat(),
                        existing[0],
                    ),
                )
                logger.info(
                    f"Updated autocorrect settings for user {user_id}: enabled={enabled}, penalty={penalty_per_correction}"
                )
            else:
                # Insert new record with default values for other columns
                await db.execute(
                    """INSERT INTO user_autocorrect_settings 
                       (user_id, enabled, penalty_per_correction, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        user_id,
                        enabled,
                        penalty_per_correction,
                        datetime.now().isoformat(),
                    ),
                )
                logger.info(
                    f"Created new autocorrect settings for user {user_id}: enabled={enabled}, penalty={penalty_per_correction}"
                )
            await db.commit()

    @retry_db_operation()
    async def log_autocorrect_usage(
        self,
        user_id: int,
        original_text: str,
        corrected_text: str,
        corrections_count: int,
    ):
        """Log autocorrect usage for analytics (optional)."""
        # For now, we'll just log this to the logger, but we could add a table for this later
        logger.info(
            f"Autocorrect used for user {user_id}: {corrections_count} corrections made"
        )

    @retry_db_operation()
    async def cleanup_duplicate_settings(self):
        """Remove duplicate autocorrect settings, keeping only the most recent entry per user."""
        async with self.get_connection() as db:
            # First, count how many duplicates we have
            cursor = await db.execute(
                """
                SELECT user_id, COUNT(*) as count 
                FROM user_autocorrect_settings 
                GROUP BY user_id 
                HAVING COUNT(*) > 1
                """
            )
            duplicates = await cursor.fetchall()

            if not duplicates:
                logger.info("✅ No duplicate autocorrect settings found")
                return 0

            total_duplicates = sum(
                row[1] - 1 for row in duplicates
            )  # -1 because we keep one record per user
            logger.info(
                f"🔄 Found {len(duplicates)} users with duplicate autocorrect settings ({total_duplicates} total duplicates)"
            )

            # Delete all but the most recent record for each user
            deleted_count = 0
            for user_id, count in duplicates:
                # Keep only the record with the highest id (most recent)
                cursor = await db.execute(
                    """
                    DELETE FROM user_autocorrect_settings 
                    WHERE user_id = ? AND id NOT IN (
                        SELECT id FROM user_autocorrect_settings 
                        WHERE user_id = ? 
                        ORDER BY created_at DESC, id DESC 
                        LIMIT 1
                    )
                    """,
                    (user_id, user_id),
                )
                deleted_count += cursor.rowcount

            await db.commit()
            logger.info(
                f"✅ Cleaned up {deleted_count} duplicate autocorrect settings entries"
            )
            return deleted_count
