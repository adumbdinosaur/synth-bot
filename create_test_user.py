#!/usr/bin/env python3
import asyncio
import aiosqlite
import sys
import os

# Add the project path to import the auth module
sys.path.append("/mnt/projects/new-tg-user-bot")

from app.auth import get_password_hash


async def create_test_user():
    try:
        db = await aiosqlite.connect("app.db")

        # Create a test user with known credentials
        username = "testuser"
        password = "testpass123"
        email = "test@login.com"
        hashed_password = get_password_hash(password)

        # Check if user already exists
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        )
        existing = await cursor.fetchone()

        if existing:
            print(f"User '{username}' already exists with ID {existing[0]}")
        else:
            # Insert new test user
            await db.execute(
                """
                INSERT INTO users (username, email, hashed_password, energy, energy_recharge_rate, last_energy_update)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
                (username, email, hashed_password, 100, 1),
            )
            await db.commit()
            print(f"✅ Created test user:")
            print(f"   Username: {username}")
            print(f"   Password: {password}")
            print(f"   Email: {email}")

        await db.close()
    except Exception as e:
        print(f"❌ Error creating test user: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(create_test_user())
