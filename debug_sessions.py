#!/usr/bin/env python3
"""
Debug script to understand session detection.
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database_manager import init_database_manager, get_database_manager
from app.telegram_client import get_telegram_manager


async def debug_sessions():
    """Debug session detection."""
    await init_database_manager()
    db_manager = get_database_manager()

    print("🔍 Debugging session detection...")

    # Check telegram manager
    telegram_manager = get_telegram_manager()
    if not telegram_manager:
        print("❌ No telegram manager found")
        return

    print(
        f"✅ Telegram manager found with {telegram_manager.get_client_count()} clients"
    )

    # Check client for user 2
    client = await telegram_manager.get_client(2)
    if not client:
        print("❌ No client found for user 2")
        return

    print(f"✅ Client found for user 2")

    try:
        is_connected = client.is_connected  # Property, not method
        print(f"📡 Client is_connected: {is_connected}")

        is_auth = await client.is_fully_authenticated()
        print(f"🔐 Client is_fully_authenticated: {is_auth}")

        result = is_connected and is_auth
        print(f"🔗 Combined result: {result}")

    except Exception as e:
        print(f"❌ Error checking client status: {e}")

    # Test our function directly
    print(f"\n🧪 Testing has_active_telegram_session function...")
    has_session = await db_manager.has_active_telegram_session(2)
    print(f"📊 Function result: {has_session}")


if __name__ == "__main__":
    asyncio.run(debug_sessions())
