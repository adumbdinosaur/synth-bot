#!/usr/bin/env python3
"""
Quick script to create a test user for login testing
"""

import asyncio
import aiosqlite
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_simple_test_user():
    """Create a simple test user with known credentials"""
    try:
        db = await aiosqlite.connect("app.db")

        # Test user credentials
        username = "admin"
        password = "admin123"
        email = "admin@test.com"
        hashed_password = pwd_context.hash(password)

        # Check if user exists
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        )
        existing = await cursor.fetchone()

        if existing:
            print(f"User '{username}' already exists with ID {existing[0]}")
        else:
            # Create user
            await db.execute(
                """
                INSERT INTO users (username, email, hashed_password, energy, energy_recharge_rate, last_energy_update)
                VALUES (?, ?, ?, 100, 1, datetime('now'))
            """,
                (username, email, hashed_password),
            )
            await db.commit()
            print(f"✅ Created test user: {username} / {password}")

        await db.close()
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(create_simple_test_user())
