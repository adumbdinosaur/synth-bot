#!/usr/bin/env python3
"""
Script to create the first admin user for the Telegram UserBot system.
"""

import asyncio
import os
import sys
from getpass import getpass

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database_manager import init_database_manager, get_database_manager
from app.auth import get_password_hash


async def create_first_admin():
    """Create the first admin user."""
    print("🛡️  Creating First Admin User")
    print("=" * 50)

    # Initialize database
    try:
        await init_database_manager()
        db_manager = get_database_manager()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return False

    # Check if any admin users already exist
    try:
        users = await db_manager.get_all_users()
        admin_users = [user for user in users if user.get("is_admin")]

        if admin_users:
            print(f"⚠️  Found {len(admin_users)} existing admin user(s):")
            for admin in admin_users:
                print(f"   - {admin['username']} ({admin['email']})")

            response = (
                input("\nDo you want to create another admin user? (y/N): ")
                .strip()
                .lower()
            )
            if response != "y":
                print("Exiting...")
                return True

    except Exception as e:
        print(f"❌ Error checking existing users: {e}")
        return False

    # Get admin user details
    print("\nEnter details for the new admin user:")
    print("-" * 40)

    while True:
        username = input("Username: ").strip()
        if not username:
            print("❌ Username cannot be empty")
            continue
        if len(username) < 3:
            print("❌ Username must be at least 3 characters")
            continue

        # Check if username exists
        try:
            existing_user = await db_manager.get_user_by_username(username)
            if existing_user:
                print("❌ Username already exists")
                continue
        except Exception as e:
            print(f"❌ Error checking username: {e}")
            continue

        break

    while True:
        email = input("Email: ").strip()
        if not email or "@" not in email:
            print("❌ Please enter a valid email address")
            continue
        break

    while True:
        password = getpass("Password (min 8 chars): ")
        if len(password) < 8:
            print("❌ Password must be at least 8 characters")
            continue

        confirm_password = getpass("Confirm password: ")
        if password != confirm_password:
            print("❌ Passwords do not match")
            continue
        break

    # Create the admin user
    try:
        hashed_password = get_password_hash(password)
        user_id = await db_manager.create_admin_user(username, email, hashed_password)

        # Initialize default settings
        await db_manager.init_user_energy_costs(user_id)
        from app.database_manager import init_user_profile_protection

        await init_user_profile_protection(user_id)

        print("\n✅ Admin user created successfully!")
        print(f"   User ID: {user_id}")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print("   Admin Status: ✅ Yes")

        print("\n🚀 You can now login at: http://localhost:8000/login")
        print("   Then access the admin panel at: http://localhost:8000/admin")

        return True

    except Exception as e:
        print(f"❌ Failed to create admin user: {e}")
        return False


if __name__ == "__main__":
    print("Telegram UserBot - Admin Setup")
    print("=" * 50)

    success = asyncio.run(create_first_admin())

    if success:
        print("\n🎉 Setup completed successfully!")
    else:
        print("\n💥 Setup failed!")
        sys.exit(1)
