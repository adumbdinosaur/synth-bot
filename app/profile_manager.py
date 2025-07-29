"""
ProfileManager - Dedicated class for monitoring and reverting profile changes
"""

import logging
import os
from typing import Dict, Any, Optional
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import DeletePhotosRequest, UploadProfilePhotoRequest
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

                # Download and store original profile photo if exists
                if profile_data["profile_photo_id"]:
                    logger.info(
                        f"📸 Downloading original profile photo (ID: {profile_data['profile_photo_id']})..."
                    )
                    photo_path = await self._download_profile_photo(
                        profile_data["profile_photo_id"], save_as_original=True
                    )
                    if photo_path:
                        logger.info(
                            f"📸 Stored original profile photo at: {photo_path}"
                        )
                    else:
                        logger.warning("⚠️ Failed to download original profile photo")
                else:
                    logger.info(
                        "📸 No profile photo to store (user has no profile photo)"
                    )

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

                # Ensure we have the original profile photo file
                if self.original_profile["profile_photo_id"]:
                    original_photo_path = self._get_original_profile_photo_path()
                    logger.info(
                        f"📸 Checking for original profile photo (ID: {self.original_profile['profile_photo_id']}) at: {original_photo_path}"
                    )
                    if not os.path.exists(original_photo_path):
                        logger.warning(
                            "🔍 Original profile photo file missing, re-downloading..."
                        )
                        photo_path = await self._download_profile_photo(
                            self.original_profile["profile_photo_id"],
                            save_as_original=True,
                        )
                        if photo_path:
                            logger.info("📸 Re-downloaded original profile photo")
                        else:
                            logger.error(
                                "❌ Failed to re-download original profile photo"
                            )
                    else:
                        logger.info("📸 Original profile photo file already exists")
                else:
                    logger.info(
                        "📸 No original profile photo to check (user had no profile photo)"
                    )

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

        # Check profile photo (normalize None values for comparison)
        current_photo = current_profile.get("profile_photo_id")
        original_photo = self.original_profile.get("profile_photo_id")

        # Normalize None/empty values to None for consistent comparison
        current_photo = current_photo if current_photo else None
        original_photo = original_photo if original_photo else None

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

            # Check profile photo changes
            current_photo = current_profile.get("profile_photo_id")
            original_photo = self.original_profile.get("profile_photo_id")
            if current_photo != original_photo:
                if original_photo and current_photo:
                    changes.append(
                        f"profile_photo: changed (ID: {original_photo} → {current_photo})"
                    )
                elif original_photo and not current_photo:
                    changes.append("profile_photo: removed")
                elif not original_photo and current_photo:
                    changes.append(f"profile_photo: added (ID: {current_photo})")

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
                        logger.info(
                            f"⚡ Applied energy penalty: -{penalty} (Energy: {result['energy']}/100)"
                        )
                    else:
                        logger.warning(
                            f"⚡ Energy penalty failed: {result.get('error', 'Unknown error')}"
                        )

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

            # Handle profile photo reversion
            await self._revert_profile_photo()

            logger.info("✅ Profile reverted successfully")

            # Get the updated profile with new photo ID after reversion
            updated_profile = await self.get_current_profile()
            if updated_profile:
                # Update current profile cache with actual current state
                self.current_profile = updated_profile.copy()

                # Update the original profile photo ID in database if photo was reverted
                original_photo_id = self.original_profile.get("profile_photo_id")
                current_photo_id = updated_profile.get("profile_photo_id")

                # If we had an original photo and now have a photo (successful revert)
                if (
                    original_photo_id
                    and current_photo_id
                    and current_photo_id != original_photo_id
                ):
                    logger.info(
                        f"📸 Updating original photo ID: {original_photo_id} → {current_photo_id}"
                    )
                    # Update the original profile with the new photo ID
                    self.original_profile["profile_photo_id"] = current_photo_id

                    # Update in database
                    if self.db_manager:
                        await self.db_manager.store_original_profile(
                            self.user_id,
                            first_name=self.original_profile["first_name"],
                            last_name=self.original_profile["last_name"],
                            bio=self.original_profile["bio"],
                            profile_photo_id=current_photo_id,
                        )
                        logger.info("💾 Updated original profile photo ID in database")
            else:
                # Fallback to original profile copy
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

            # Clean up old profile photo if photo is changing
            old_photo_id = (
                self.original_profile.get("profile_photo_id")
                if self.original_profile
                else None
            )
            new_photo_id = new_profile_data.get("profile_photo_id")

            if old_photo_id != new_photo_id:
                await self._cleanup_old_profile_photo()

            await self.db_manager.store_original_profile(
                self.user_id,
                first_name=new_profile_data.get("first_name", ""),
                last_name=new_profile_data.get("last_name", ""),
                bio=new_profile_data.get("bio", ""),
                profile_photo_id=new_profile_data.get("profile_photo_id"),
            )

            # Download and store new original profile photo if exists
            if new_photo_id:
                photo_path = await self._download_profile_photo(
                    new_photo_id, save_as_original=True
                )
                if photo_path:
                    logger.info("📸 Updated original profile photo")
                else:
                    logger.warning("⚠️ Failed to download updated profile photo")

            self.original_profile = new_profile_data.copy()
            logger.info("💾 Updated original profile data")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating original profile: {e}")
            return False

    async def update_profile(
        self,
        first_name: str = None,
        last_name: str = None,
        bio: str = None,
        profile_photo_file: str = None,
    ) -> bool:
        """
        Update the user's profile with new data. This changes the actual Telegram profile.
        """
        try:
            logger.info(f"🔄 Updating profile for user {self.user_id}")

            # Get current profile first
            current_profile = await self.get_current_profile()
            if not current_profile:
                logger.error("❌ Could not get current profile")
                return False

            # Build update data - use current values if new ones not provided
            update_data = {
                "first_name": first_name
                if first_name is not None
                else current_profile.get("first_name", ""),
                "last_name": last_name
                if last_name is not None
                else current_profile.get("last_name", ""),
                "bio": bio if bio is not None else current_profile.get("bio", ""),
            }

            # Update name and bio
            await self.client(
                UpdateProfileRequest(
                    first_name=update_data["first_name"],
                    last_name=update_data["last_name"],
                    about=update_data["bio"],
                )
            )
            logger.info("✅ Updated profile name and bio")

            # Handle profile photo update if provided
            if profile_photo_file:
                logger.info("📸 Updating profile photo...")
                success = await self._upload_profile_photo(profile_photo_file)
                if success:
                    logger.info("✅ Profile photo updated")
                else:
                    logger.error("❌ Failed to update profile photo")
                    return False

            # Update current profile cache
            self.current_profile = await self.get_current_profile()

            logger.info("✅ Profile updated successfully")
            return True

        except FloodWaitError as e:
            logger.warning(
                f"⏰ Flood wait for {e.seconds} seconds when updating profile"
            )
            await asyncio.sleep(e.seconds)
            return await self.update_profile(
                first_name, last_name, bio, profile_photo_file
            )
        except Exception as e:
            logger.error(f"❌ Error updating profile: {e}")
            return False

    async def save_current_as_original(self) -> bool:
        """
        Save the current profile state as the new 'original' profile.
        This updates what the system considers the baseline profile.
        """
        try:
            logger.info(
                f"💾 Saving current profile as new original for user {self.user_id}"
            )

            # Get current profile
            current_profile = await self.get_current_profile()
            if not current_profile:
                logger.error("❌ Could not get current profile to save")
                return False

            # Update the original profile in memory and database
            success = await self.update_original_profile(current_profile)
            if success:
                logger.info("✅ Current profile saved as new original")
                return True
            else:
                logger.error("❌ Failed to save current profile as original")
                return False

        except Exception as e:
            logger.error(f"❌ Error saving current profile as original: {e}")
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

    async def _revert_profile_photo(self):
        """Revert profile photo to original state"""
        try:
            current_profile = await self.get_current_profile()
            if not current_profile:
                logger.warning("❌ Could not get current profile for photo reversion")
                return

            current_photo_id = current_profile.get("profile_photo_id")
            original_photo_id = self.original_profile.get("profile_photo_id")

            # If photos are the same, no reversion needed
            if current_photo_id == original_photo_id:
                logger.debug("📸 Profile photo unchanged, no reversion needed")
                return

            # If user added a photo but originally had none, remove it
            if current_photo_id and not original_photo_id:
                logger.info("📸 Removing added profile photo...")
                try:
                    # Get current profile photos and delete them
                    photos = await self.client.get_profile_photos("me")
                    if photos:
                        # Delete all profile photos (Telegram API deletes the most recent)
                        await self.client(DeletePhotosRequest(photos))
                        logger.info("✅ Profile photo removed successfully")
                    else:
                        logger.debug("📸 No profile photo to remove")
                except Exception as e:
                    logger.error(f"❌ Error removing profile photo: {e}")

            # If user changed photo and originally had one, restore the original
            elif (
                current_photo_id
                and original_photo_id
                and current_photo_id != original_photo_id
            ):
                logger.info("📸 Restoring original profile photo...")
                original_photo_path = self._get_original_profile_photo_path()

                if os.path.exists(original_photo_path):
                    # Remove current photo first
                    try:
                        photos = await self.client.get_profile_photos("me")
                        if photos:
                            await self.client(DeletePhotosRequest(photos))
                            logger.debug("📸 Removed current profile photo")
                    except Exception as e:
                        logger.warning(f"⚠️ Error removing current photo: {e}")

                    # Upload original photo
                    success = await self._upload_profile_photo(original_photo_path)
                    if success:
                        logger.info("✅ Original profile photo restored successfully")
                    else:
                        logger.error("❌ Failed to restore original profile photo")
                else:
                    logger.warning(
                        f"⚠️ Original profile photo file not found: {original_photo_path}. "
                        "Cannot restore automatically."
                    )

            # If user removed photo but originally had one, restore it
            elif not current_photo_id and original_photo_id:
                logger.info("📸 Restoring removed profile photo...")
                original_photo_path = self._get_original_profile_photo_path()

                if os.path.exists(original_photo_path):
                    success = await self._upload_profile_photo(original_photo_path)
                    if success:
                        logger.info("✅ Removed profile photo restored successfully")
                    else:
                        logger.error("❌ Failed to restore removed profile photo")
                else:
                    logger.warning(
                        f"⚠️ Original profile photo file not found: {original_photo_path}. "
                        "Cannot restore automatically."
                    )

        except Exception as e:
            logger.error(f"❌ Error reverting profile photo: {e}")

    async def _download_profile_photo(
        self, photo_id: str, save_as_original: bool = False
    ) -> Optional[str]:
        """Download and store a profile photo"""
        try:
            logger.debug(f"📸 Attempting to download profile photo with ID: {photo_id}")

            # Get the user's profile photos
            photos = await self.client.get_profile_photos(
                "me", limit=10
            )  # Get more photos to find the right one

            if not photos:
                logger.warning("📸 No profile photos found for user")
                return None

            logger.debug(f"📸 Found {len(photos)} profile photos")

            # Try to find the photo with matching ID
            target_photo = None
            for photo in photos:
                if hasattr(photo, "id") and str(photo.id) == photo_id:
                    target_photo = photo
                    logger.debug(f"📸 Found matching photo with ID: {photo_id}")
                    break

            # If we can't find the exact photo, use the first one (most recent)
            if not target_photo:
                logger.warning(
                    f"📸 Could not find photo with ID {photo_id}, using most recent photo"
                )
                target_photo = photos[0]
                if hasattr(target_photo, "id"):
                    logger.debug(f"📸 Using photo with ID: {target_photo.id}")

            # Determine file path
            if save_as_original:
                file_path = self._get_original_profile_photo_path()
            else:
                file_path = self._get_profile_photo_path(photo_id)

            logger.debug(f"📸 Saving photo to: {file_path}")

            # Download the photo
            await self.client.download_media(target_photo, file_path)
            logger.info(f"📸 Downloaded profile photo to: {file_path}")

            return file_path

        except Exception as e:
            logger.error(f"❌ Error downloading profile photo: {e}")
            return None

    async def _upload_profile_photo(self, file_path: str) -> bool:
        """Upload a profile photo from file"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"❌ Profile photo file not found: {file_path}")
                return False

            # Upload the file first
            uploaded_file = await self.client.upload_file(file_path)

            # Use UploadProfilePhotoRequest with the uploaded file
            await self.client(UploadProfilePhotoRequest(file=uploaded_file))

            logger.info(f"📸 Profile photo uploaded from: {file_path}")
            return True

        except FloodWaitError as e:
            logger.warning(
                f"⏰ Flood wait for {e.seconds} seconds when uploading photo"
            )
            await asyncio.sleep(e.seconds)
            return await self._upload_profile_photo(file_path)
        except Exception as e:
            logger.error(f"❌ Error uploading profile photo: {e}")
            return False

    def _get_profile_photos_dir(self) -> str:
        """Get the directory for storing profile photos"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        photos_dir = os.path.join(base_dir, "data", "profile_photos")
        os.makedirs(photos_dir, exist_ok=True)
        return photos_dir

    def _get_profile_photo_path(self, photo_id: str) -> str:
        """Get the file path for storing a specific profile photo"""
        photos_dir = self._get_profile_photos_dir()
        return os.path.join(photos_dir, f"user_{self.user_id}_photo_{photo_id}.jpg")

    def _get_original_profile_photo_path(self) -> str:
        """Get the file path for the original profile photo"""
        photos_dir = self._get_profile_photos_dir()
        return os.path.join(photos_dir, f"user_{self.user_id}_original.jpg")

    async def _cleanup_old_profile_photo(self):
        """Clean up old profile photo files"""
        try:
            original_photo_path = self._get_original_profile_photo_path()
            if os.path.exists(original_photo_path):
                os.remove(original_photo_path)
                logger.debug("🗑️ Cleaned up old original profile photo")
        except Exception as e:
            logger.warning(f"⚠️ Error cleaning up old profile photo: {e}")

    def get_profile_photo_url(self) -> Optional[str]:
        """Get URL path for current profile photo if it exists locally"""
        try:
            if self.current_profile and self.current_profile.get("profile_photo_id"):
                original_photo_path = self._get_original_profile_photo_path()
                if os.path.exists(original_photo_path):
                    # Return relative path for web serving
                    return f"/static/profile_photos/user_{self.user_id}_original.jpg"
            return None
        except Exception as e:
            logger.error(f"❌ Error getting profile photo URL: {e}")
            return None

    def get_original_profile_photo_url(self) -> Optional[str]:
        """Get URL path for original profile photo if it exists locally"""
        try:
            if self.original_profile and self.original_profile.get("profile_photo_id"):
                original_photo_path = self._get_original_profile_photo_path()
                if os.path.exists(original_photo_path):
                    # Return relative path for web serving
                    return f"/static/profile_photos/user_{self.user_id}_original.jpg"
            return None
        except Exception as e:
            logger.error(f"❌ Error getting original profile photo URL: {e}")
            return None

    async def _backup_current_profile_photo(self, current_profile: Dict[str, Any]):
        """Backup current profile photo before reversion (for forensic purposes)"""
        try:
            current_photo_id = current_profile.get("profile_photo_id")
            if current_photo_id:
                # Create backup with timestamp
                import datetime

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(
                    self._get_profile_photos_dir(),
                    f"user_{self.user_id}_backup_{timestamp}_{current_photo_id}.jpg",
                )

                photos = await self.client.get_profile_photos("me", limit=1)
                if photos:
                    await self.client.download_media(photos[0], backup_path)
                    logger.info(f"📸 Backed up current profile photo: {backup_path}")
                    return backup_path

            return None

        except Exception as e:
            logger.warning(f"⚠️ Error backing up current profile photo: {e}")
            return None
