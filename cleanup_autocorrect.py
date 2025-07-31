#!/usr/bin/env python3
"""
Database cleanup script for autocorrect settings.
Removes duplicate entries, keeping only the most recent one per user.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from app.database import get_database_manager
except ImportError as e:
    print(f"Error importing database manager: {e}")
    print("Make sure you're running this script from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("cleanup.log", mode="a"),
    ],
)

logger = logging.getLogger(__name__)


async def cleanup_autocorrect_duplicates():
    """Main cleanup function for autocorrect settings."""
    try:
        logger.info("🧹 Starting autocorrect settings cleanup...")

        # Initialize database manager
        db_manager = get_database_manager()

        # Run the cleanup
        deleted_count = await db_manager.autocorrect.cleanup_duplicate_settings()

        if deleted_count > 0:
            logger.info(f"🗑️ Successfully removed {deleted_count} duplicate entries")
        else:
            logger.info("✨ Database is already clean")

        return deleted_count

    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        import traceback

        traceback.print_exc()
        return -1


async def verify_cleanup():
    """Verify that the cleanup was successful."""
    try:
        db_manager = get_database_manager()

        async with db_manager.get_connection() as db:
            # Check for any remaining duplicates
            cursor = await db.execute("""
                SELECT user_id, COUNT(*) as count 
                FROM user_autocorrect_settings 
                GROUP BY user_id 
                HAVING COUNT(*) > 1
            """)
            duplicates = await cursor.fetchall()

            if duplicates:
                logger.warning(
                    f"⚠️ Still found {len(duplicates)} users with duplicates after cleanup"
                )
                for user_id, count in duplicates:
                    logger.warning(f"  User {user_id}: {count} entries")
                return False
            else:
                logger.info("✅ Verification passed: No duplicate entries found")
                return True

    except Exception as e:
        logger.error(f"❌ Error during verification: {e}")
        return False


async def main():
    """Main function."""
    logger.info("🚀 Database cleanup script started")

    # Run cleanup
    deleted_count = await cleanup_autocorrect_duplicates()

    if deleted_count < 0:
        logger.error("💥 Cleanup failed")
        sys.exit(1)

    # Verify results
    if not await verify_cleanup():
        logger.error("💥 Verification failed")
        sys.exit(1)

    logger.info("🎉 Database cleanup completed successfully")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Cleanup interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)
