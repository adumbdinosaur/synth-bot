#!/usr/bin/env python3
"""
Script to verify database configuration is working correctly.
"""

import os
import sys


def main():
    print("=== Database Configuration Verification ===")

    # Check environment variable
    database_url = os.getenv("DATABASE_URL", "Not set")
    print(f"DATABASE_URL: {database_url}")

    if database_url.startswith("sqlite:///"):
        database_path = database_url[10:]  # Remove 'sqlite:///' prefix
        if database_path.startswith("./"):
            absolute_path = os.path.join(os.getcwd(), database_path[2:])
        else:
            absolute_path = database_path

        print(f"Resolved database path: {absolute_path}")
        print(f"Database directory: {os.path.dirname(absolute_path)}")
        print(f"Directory exists: {os.path.exists(os.path.dirname(absolute_path))}")
        print(f"Database file exists: {os.path.exists(absolute_path)}")

        # Check if we can create the directory
        try:
            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            print("✅ Database directory is accessible")
        except Exception as e:
            print(f"❌ Error creating database directory: {e}")
            return 1
    else:
        print("❌ DATABASE_URL is not a SQLite URL")
        return 1

    print("\n=== Testing Database Manager Import ===")
    try:
        from app.database import get_database_manager

        db_manager = get_database_manager()
        print(f"✅ Database manager created with path: {db_manager.database_path}")
    except Exception as e:
        print(f"❌ Error creating database manager: {e}")
        return 1

    print("\n✅ Database configuration verification completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
