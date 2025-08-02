#!/usr/bin/env python3
"""
Migration script to add custom redactions table to existing databases.
Run this script to add the custom redactions feature to existing installations.
"""

import asyncio
import logging
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_database():
    """Add custom redactions table to database."""
    try:
        db_manager = get_database_manager()

        logger.info("🔄 Starting database migration for custom redactions...")

        async with db_manager.get_connection() as db:
            # Check if table already exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_custom_redactions'"
            )
            existing_table = await cursor.fetchone()

            if existing_table:
                logger.info(
                    "✅ Custom redactions table already exists, migration not needed"
                )
                return

            # Create the custom redactions table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_custom_redactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    original_word TEXT NOT NULL,
                    replacement_word TEXT NOT NULL,
                    penalty INTEGER NOT NULL DEFAULT 5,
                    case_sensitive BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    UNIQUE(user_id, original_word)
                )
                """
            )

            await db.commit()
            logger.info("✅ Custom redactions table created successfully")

            # Verify table creation
            cursor = await db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_custom_redactions'"
            )
            table_schema = await cursor.fetchone()

            if table_schema:
                logger.info("✅ Migration completed successfully")
                logger.info(f"📋 Table schema: {table_schema[0]}")
            else:
                logger.error("❌ Migration verification failed")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


async def main():
    """Main migration function."""
    try:
        await migrate_database()
        logger.info("🎉 Database migration completed successfully!")
    except Exception as e:
        logger.error(f"💥 Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
