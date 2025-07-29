#!/usr/bin/env python3
import asyncio
import aiosqlite


async def check_database():
    try:
        db = await aiosqlite.connect("app.db")

        # Check users table
        cursor = await db.execute("SELECT id, username, email FROM users")
        users = await cursor.fetchall()
        print(f"Users in database: {users}")

        # Check table schema
        cursor = await db.execute("PRAGMA table_info(users)")
        schema = await cursor.fetchall()
        print(f"Users table schema: {schema}")

        await db.close()
    except Exception as e:
        print(f"Database error: {e}")


if __name__ == "__main__":
    asyncio.run(check_database())
