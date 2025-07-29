"""
ProfileManager - Dedicated class for monitoring and reverting profile changes
"""

import logging
from typing import Dict, Any, Optional
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.errors import FloodWaitError
import asyncio

logger = logging.getLogger(__name__)


class ProfileManager:
    """
    Dedicated class for monitoring and reverting profile changes.
    Uses GetFullUser request to get complete profile data including bio.
    """

    def __init__(self, user_id: int, username: str, client: TelegramClient):
        self.user_id = user_id
        self.username = username
        self.client = client
        self.db_manager = None  # Will be set by telegram_client
        self.original_profile = None
        self.current_profile = None
        self.monitoring = False

    def set_db_manager(self, db_manager):
        """Set the database manager instance"""
        self.db_manager = db_manager

    async def initialize(self):
        """Initialize the ProfileManager by loading/storing original profile"""
        try:
            logger.info(f"🎯 Initializing ProfileManager for user {self.user_id}")

            # Get current profile data using GetFullUser
            current_profile = await self.get_current_profile()

            if current_profile:
                # Store as original profile if not exists
                await self._store_original_profile_if_needed(current_profile)
                self.current_profile = current_profile
                logger.info("✅ ProfileManager initialized successfully")
                return True
            else:
                logger.error("❌ Failed to get current profile data")
                return False

        except Exception as e:
            logger.error(f"❌ Error initializing ProfileManager: {e}")
            return False

    async def get_current_profile(self) -> Optional[Dict[str, Any]]:
        """
        Get current profile data using GetFullUser request.
        This is the only way to get the bio (accessible via 'about').
        """
        try:
            # Get full user data including bio
            full_user = await self.client(GetFullUserRequest("me"))
            user = full_user.users[0]

            profile_data = {
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "bio": full_user.full_user.about or "",  # Bio from GetFullUser
                "username": user.username or "",
                "profile_photo_id": None,
            }

            # Get profile photo ID if exists
            if user.photo and hasattr(user.photo, "photo_id"):
                profile_data["profile_photo_id"] = str(user.photo.photo_id)

            logger.debug(f"📱 Current profile: {profile_data}")
            return profile_data

        except FloodWaitError as e:
            logger.warning(
                f"⏰ Flood wait for {e.seconds} seconds when getting profile"
            )
            await asyncio.sleep(e.seconds)
            return await self.get_current_profile()
        except Exception as e:
            logger.error(f"❌ Error getting current profile: {e}")
            return None

    async def _store_original_profile_if_needed(self, profile_data: Dict[str, Any]):
        """Store original profile data if not already stored"""
        try:
            if not self.db_manager:
                logger.error("❌ Database manager not set")
                return

            # Check if original profile already exists
            settings = await self.db_manager.get_profile_protection_settings(
                self.user_id
            )

            if not settings.get("profile_protection_enabled", False):
                # Store original profile
                await self.db_manager.store_original_profile(
                    self.user_id,
                    first_name=profile_data["first_name"],
                    last_name=profile_data["last_name"],
                    bio=profile_data["bio"],
                    profile_photo_id=profile_data["profile_photo_id"],
                )
                logger.info("💾 Stored original profile data")
                self.original_profile = profile_data.copy()
            else:
                # Load existing original profile
                self.original_profile = {
                    "first_name": settings.get("original_first_name", ""),
                    "last_name": settings.get("original_last_name", ""),
                    "bio": settings.get("original_bio", ""),
                    "profile_photo_id": settings.get("original_profile_photo_id"),
                }
                logger.info("📂 Loaded existing original profile data")

        except Exception as e:
            logger.error(f"❌ Error storing/loading original profile: {e}")

    async def start_monitoring(self):
        """Start monitoring profile changes"""
        if self.monitoring:
            logger.warning("⚠️ Profile monitoring already active")
            return

        self.monitoring = True
        logger.info(f"👁️ Started profile monitoring for user {self.user_id}")

        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())

    async def stop_monitoring(self):
        """Stop monitoring profile changes"""
        self.monitoring = False
        logger.info(f"🛑 Stopped profile monitoring for user {self.user_id}")

    async def _monitoring_loop(self):
        """Main monitoring loop to detect profile changes"""
        try:
            while self.monitoring:
                await asyncio.sleep(30)  # Check every 30 seconds

                if not self.monitoring:
                    break

                current = await self.get_current_profile()
                if current and self._has_profile_changed(current):
                    logger.warning("🚨 Profile change detected!")
                    await self._handle_profile_change(current)

        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
            self.monitoring = False

    def _has_profile_changed(self, current_profile: Dict[str, Any]) -> bool:
        """Check if profile has changed from original"""
        if not self.original_profile:
            return False

        # Compare key fields
        for key in ["first_name", "last_name", "bio"]:
            if current_profile.get(key, "") != self.original_profile.get(key, ""):
                return True

        # Check profile photo (basic comparison)
        current_photo = current_profile.get("profile_photo_id")
        original_photo = self.original_profile.get("profile_photo_id")

        if current_photo != original_photo:
            return True

        return False

    async def _handle_profile_change(self, current_profile: Dict[str, Any]):
        """Handle detected profile change"""
        try:
            # Log the change
            changes = []
            for key in ["first_name", "last_name", "bio"]:
                original_val = self.original_profile.get(key, "")
                current_val = current_profile.get(key, "")
                if original_val != current_val:
                    changes.append(f"{key}: '{original_val}' → '{current_val}'")

            if changes:
                logger.warning(f"📝 Profile changes detected: {', '.join(changes)}")

            # Apply energy penalty if configured
            if self.db_manager:
                penalty = await self.db_manager.get_profile_change_penalty(self.user_id)
                if penalty > 0:
                    result = await self.db_manager.consume_user_energy(
                        self.user_id, penalty
                    )
                    if result["success"]:
                        logger.info(f"⚡ Applied energy penalty: -{penalty} (Energy: {result['energy']}/100)")
                    else:
                        logger.warning(f"⚡ Energy penalty failed: {result.get('error', 'Unknown error')}")

            # Revert profile changes
            await self.revert_to_original_profile()

        except Exception as e:
            logger.error(f"❌ Error handling profile change: {e}")

    async def revert_to_original_profile(self):
        """Revert profile back to original state"""
        try:
            if not self.original_profile:
                logger.error("❌ No original profile data to revert to")
                return False

            logger.info("🔄 Reverting profile to original state...")

            # Revert name and bio
            await self.client(
                UpdateProfileRequest(
                    first_name=self.original_profile["first_name"],
                    last_name=self.original_profile["last_name"],
                    about=self.original_profile["bio"],
                )
            )

            logger.info("✅ Profile reverted successfully")

            # Update current profile cache
            self.current_profile = self.original_profile.copy()

            return True

        except FloodWaitError as e:
            logger.warning(
                f"⏰ Flood wait for {e.seconds} seconds when reverting profile"
            )
            await asyncio.sleep(e.seconds)
            return await self.revert_to_original_profile()
        except Exception as e:
            logger.error(f"❌ Error reverting profile: {e}")
            return False

    async def update_original_profile(self, new_profile_data: Dict[str, Any]):
        """Update the stored original profile data"""
        try:
            if not self.db_manager:
                logger.error("❌ Database manager not set")
                return False

            await self.db_manager.store_original_profile(
                self.user_id,
                first_name=new_profile_data.get("first_name", ""),
                last_name=new_profile_data.get("last_name", ""),
                bio=new_profile_data.get("bio", ""),
                profile_photo_id=new_profile_data.get("profile_photo_id"),
            )

            self.original_profile = new_profile_data.copy()
            logger.info("💾 Updated original profile data")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating original profile: {e}")
            return False

    async def get_profile_status(self) -> Dict[str, Any]:
        """Get current profile monitoring status"""
        try:
            current = await self.get_current_profile()

            return {
                "monitoring": self.monitoring,
                "has_original": self.original_profile is not None,
                "current_profile": current,
                "original_profile": self.original_profile,
                "changes_detected": self._has_profile_changed(current)
                if current
                else False,
            }

        except Exception as e:
            logger.error(f"❌ Error getting profile status: {e}")
            return {"error": str(e)}
