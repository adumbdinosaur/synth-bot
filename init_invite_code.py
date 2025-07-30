#!/usr/bin/env python3
"""
Initialize the default invite code in the database.
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database_manager import init_database_manager, get_database_manager


async def init_invite_code():
    """Initialize the default invite code."""
    await init_database_manager()
    db_manager = get_database_manager()

    # Create the default invite code
    invite_code = "peterpepperpickedapepper"

    # Check if it already exists
    is_valid = await db_manager.validate_invite_code(invite_code)
    if is_valid:
        print(f"✅ Invite code '{invite_code}' already exists and is active")
        return

    # Create the invite code
    try:
        await db_manager.create_invite_code(
            invite_code, max_uses=None
        )  # Unlimited uses
        print(f"✅ Created invite code: '{invite_code}' (unlimited uses)")
    except Exception as e:
        # Code might already exist but be inactive, let's check
        print(f"⚠️ Could not create invite code, it may already exist: {e}")


if __name__ == "__main__":
    asyncio.run(init_invite_code())
