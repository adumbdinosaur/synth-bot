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
                "SELECT * FROM user_autocorrect_settings WHERE user_id = ?",
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
            await db.execute(
                """INSERT OR REPLACE INTO user_autocorrect_settings 
                   (user_id, enabled, penalty_per_correction, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, enabled, penalty_per_correction, datetime.now().isoformat()),
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
