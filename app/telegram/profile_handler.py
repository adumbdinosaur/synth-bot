"""
Profile handler for Telegram userbot.
Handles profile protection, monitoring, and profile-related operations.
"""

import logging
from typing import Optional, Dict, Any
from telethon import events
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class ProfileHandler(BaseHandler):
    """Handles profile-related operations for Telegram userbot."""

    def __init__(self, userbot):
        super().__init__(userbot)
        self.profile_manager = None
        self._profile_handler_registered = False

    async def initialize(self) -> bool:
        """Initialize profile handler and ProfileManager."""
        try:
            if not self.userbot.client or not await self.userbot.client.is_user_authorized():
                logger.error(
                    f"Client not authorized for user {self.userbot.user_id} ({self.userbot.username})"
                )
                return False

            # Initialize ProfileManager with client
            if not self.profile_manager:
                from ..profile_manager import ProfileManager
                
                self.profile_manager = ProfileManager(
                    self.userbot.user_id, self.userbot.username, self.userbot.client
                )
                
                # Set database manager reference
                from ..database import get_database_manager
                self.profile_manager.set_db_manager(get_database_manager())

                # Initialize the ProfileManager (this will store original profile using GetFullUser)
                initialized = await self.profile_manager.initialize()
                if initialized:
                    logger.info(
                        f"🎯 ProfileManager initialized for user {self.userbot.user_id} ({self.userbot.username})"
                    )
                    # Start monitoring profile changes
                    await self.profile_manager.start_monitoring()
                else:
                    logger.error(
                        f"❌ Failed to initialize ProfileManager for user {self.userbot.user_id}"
                    )
                    return False

            # Keep the old method for backwards compatibility, but ProfileManager handles the real work
            await self._store_original_profile()

            return True

        except Exception as e:
            logger.error(f"Error initializing profile handler for user {self.userbot.user_id}: {e}")
            return False

    async def register_handlers(self) -> bool:
        """Register profile-related event handlers."""
        if not self.userbot.client or self._profile_handler_registered:
            return False

        try:
            # Register profile change handlers
            @self.userbot.client.on(events.UserUpdate)
            async def profile_update_handler(event):
                await self._handle_profile_update(event)

            self._profile_handler_registered = True
            logger.info(
                f"Profile handlers registered for user {self.userbot.user_id} ({self.userbot.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to register profile handlers for user {self.userbot.user_id}: {e}"
            )
            return False

    async def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get current profile information for this user using ProfileManager."""
        try:
            # Use ProfileManager if available for consistent profile data
            if self.profile_manager:
                profile_data = await self.profile_manager.get_current_profile()
                if profile_data:
                    # Add phone number which ProfileManager doesn't track
                    if self.userbot.client and self.userbot.client.is_connected():
                        me = await self.userbot.client.get_me()
                        if me:
                            profile_data["phone"] = me.phone or ""
                    return profile_data

            # Fallback to direct client access if ProfileManager not available
            return await self._get_profile_direct()

        except Exception as e:
            logger.error(f"Error getting profile for user {self.userbot.user_id}: {e}")
            return None

    async def set_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Set profile information for this user."""
        try:
            if not self.userbot.client or not self.userbot.client.is_connected():
                logger.error(f"User {self.userbot.user_id} ({self.userbot.username}) not connected")
                return False

            success = True
            changes_made = []

            # Update name and bio
            success = await self._update_profile_text(profile_data, changes_made)

            # Update profile photo
            if profile_data.get("photo_url") and success:
                success = await self._update_profile_photo(profile_data["photo_url"], changes_made)

            if changes_made:
                logger.info(
                    f"Profile updated for user {self.userbot.user_id} ({self.userbot.username}): "
                    f"{', '.join(changes_made)}"
                )

            return success

        except Exception as e:
            logger.error(f"Error setting profile for user {self.userbot.user_id}: {e}")
            return False

    async def unlock_profile(self):
        """Unlock profile protection when session ends."""
        try:
            # Stop ProfileManager monitoring
            if self.profile_manager:
                await self.profile_manager.stop_monitoring()

            from ..database import get_database_manager
            db_manager = get_database_manager()
            await db_manager.clear_profile_lock(self.userbot.user_id)
            logger.info(
                f"🔓 PROFILE UNLOCKED | User: {self.userbot.username} (ID: {self.userbot.user_id})"
            )

        except Exception as e:
            logger.error(f"Error unlocking profile for user {self.userbot.user_id}: {e}")

    async def get_profile_status(self):
        """Get current profile monitoring status via ProfileManager."""
        if self.profile_manager:
            return await self.profile_manager.get_profile_status()
        else:
            return {"error": "ProfileManager not initialized"}

    async def update_original_profile(self, new_profile_data: Dict[str, Any]):
        """Update the stored original profile data via ProfileManager."""
        if self.profile_manager:
            return await self.profile_manager.update_original_profile(new_profile_data)
        else:
            logger.error(f"❌ ProfileManager not available for user {self.userbot.user_id}")
            return False

    async def trigger_profile_change(self) -> bool:
        """Trigger a profile change for this user. Returns True if successful."""
        try:
            if not self.userbot.client or not self.userbot.client.is_connected():
                logger.error(f"User {self.userbot.user_id} ({self.userbot.username}) not connected")
                return False

            # Get the database manager for profile operations
            from ..database import get_database_manager
            db_manager = get_database_manager()

            # Lock the profile (indicates session is active)
            await db_manager.lock_user_profile(self.userbot.user_id)

            logger.info(
                f"Profile change triggered for user {self.userbot.user_id} ({self.userbot.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error triggering profile change for user {self.userbot.user_id}: {e}"
            )
            return False

    async def _handle_profile_update(self, event):
        """Handle profile update events and revert unauthorized changes. (Delegated to ProfileManager)"""
        try:
            # If ProfileManager is active, let it handle the monitoring
            if self.profile_manager and self.profile_manager.monitoring:
                logger.debug(
                    f"ProfileManager handling profile monitoring for user {self.userbot.user_id}"
                )
                return

            # Fallback to legacy handling if ProfileManager not available
            logger.warning(
                f"ProfileManager not active, using legacy profile handling for user {self.userbot.user_id}"
            )
            await self._legacy_handle_profile_update(event)

        except Exception as e:
            logger.error(f"Error handling profile update for user {self.userbot.user_id}: {e}")

    async def _legacy_handle_profile_update(self, event):
        """Legacy profile update handler - kept for reference but ProfileManager should be used instead."""
        try:
            from ..database import get_database_manager
            db_manager = get_database_manager()

            # Check if this user's profile is locked
            if not await db_manager.is_profile_locked(self.userbot.user_id):
                return  # Profile not locked, allow changes

            # Use ProfileManager's revert functionality if available
            if self.profile_manager:
                success = await self.profile_manager.revert_to_original_profile()
                if success:
                    logger.info(
                        f"✅ Profile reverted using ProfileManager for user {self.userbot.user_id}"
                    )
                    # Apply energy penalty
                    penalty = await db_manager.get_profile_change_penalty(self.userbot.user_id)
                    if penalty > 0:
                        result = await db_manager.consume_user_energy(
                            self.userbot.user_id, penalty
                        )
                        if result["success"]:
                            logger.info(
                                f"⚡ Applied energy penalty: -{penalty} (Energy: {result['energy']}/100)"
                            )
                        else:
                            logger.warning(
                                f"⚡ Energy penalty failed: {result.get('error', 'Unknown error')}"
                            )
                else:
                    logger.error(
                        f"❌ Failed to revert profile using ProfileManager for user {self.userbot.user_id}"
                    )

        except Exception as e:
            logger.error(
                f"Error in legacy profile update handler for user {self.userbot.user_id}: {e}"
            )

    async def _store_original_profile(self):
        """Store the user's original profile data when session starts. (Legacy method - ProfileManager handles this now)"""
        try:
            if not self.userbot.client or not await self.userbot.client.is_user_authorized():
                logger.warning(
                    f"Cannot store profile - client not authenticated for user {self.userbot.user_id}"
                )
                return

            # Use GetFullUser to get complete profile data including bio
            from telethon.tl.functions.users import GetFullUserRequest

            full_user = await self.userbot.client(GetFullUserRequest("me"))
            me = full_user.users[0]

            if not me:
                logger.error(f"Could not get user profile for user {self.userbot.user_id}")
                return

            from ..database import get_database_manager
            db_manager = get_database_manager()

            # Get profile photo ID if exists
            profile_photo_id = None
            if me.photo:
                profile_photo_id = (
                    str(me.photo.photo_id)
                    if hasattr(me.photo, "photo_id")
                    else str(me.photo)
                )

            # Store original profile data
            await db_manager.store_original_profile(
                user_id=self.userbot.user_id,
                first_name=me.first_name,
                last_name=me.last_name,
                bio=full_user.full_user.about,  # Bio from GetFullUser
                profile_photo_id=profile_photo_id,
            )

            logger.info(
                f"🔒 PROFILE LOCKED | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                f"Profile protection enabled"
            )

        except Exception as e:
            logger.error(f"Error storing original profile for user {self.userbot.user_id}: {e}")

    async def _get_profile_direct(self) -> Optional[Dict[str, Any]]:
        """Get profile directly from Telegram client."""
        if not self.userbot.client or not self.userbot.client.is_connected():
            logger.error(f"User {self.userbot.user_id} ({self.userbot.username}) not connected")
            return None

        # Get current user info using GetFullUser (same as ProfileManager)
        from telethon.tl.functions.users import GetFullUserRequest

        full_user = await self.userbot.client(GetFullUserRequest("me"))
        me = full_user.users[0]
        if not me:
            return None

        return {
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "bio": full_user.full_user.about or "",
            "username": me.username or "",
            "phone": me.phone or "",
            "profile_photo_id": str(me.photo.photo_id)
            if me.photo and hasattr(me.photo, "photo_id")
            else None,
        }

    async def _update_profile_text(self, profile_data: Dict[str, Any], changes_made: list) -> bool:
        """Update profile text (name and bio)."""
        try:
            from telethon.tl.functions.account import UpdateProfileRequest
            
            first_name = profile_data.get("first_name")
            last_name = profile_data.get("last_name")
            bio = profile_data.get("bio")

            if first_name is not None or last_name is not None or bio is not None:
                # Get current profile to preserve existing values
                current = await self.get_profile()

                update_first_name = (
                    first_name
                    if first_name is not None
                    else (current.get("first_name", "") if current else "")
                )
                update_last_name = (
                    last_name
                    if last_name is not None
                    else (current.get("last_name", "") if current else "")
                )
                update_bio = (
                    bio
                    if bio is not None
                    else (current.get("bio", "") if current else "")
                )

                await self.userbot.client(
                    UpdateProfileRequest(
                        first_name=update_first_name,
                        last_name=update_last_name,
                        about=update_bio,
                    )
                )

                if first_name is not None:
                    changes_made.append(f"first_name: {first_name}")
                if last_name is not None:
                    changes_made.append(f"last_name: {last_name}")
                if bio is not None:
                    changes_made.append(f"bio: {bio}")

            return True

        except Exception as e:
            logger.error(f"Error updating profile text for user {self.userbot.user_id}: {e}")
            return False

    async def _update_profile_photo(self, photo_url: str, changes_made: list) -> bool:
        """Update profile photo from URL."""
        try:
            from telethon.tl.functions.photos import UploadProfilePhotoRequest
            import aiohttp

            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as response:
                    if response.status == 200:
                        photo_data = await response.read()

                        # Upload as profile photo
                        uploaded_file = await self.userbot.client.upload_file(photo_data)
                        await self.userbot.client(UploadProfilePhotoRequest(file=uploaded_file))
                        changes_made.append(f"photo: {photo_url}")
                        return True
                    else:
                        logger.error(
                            f"Failed to download photo from {photo_url}: HTTP {response.status}"
                        )
                        return False

        except Exception as e:
            logger.error(f"Error updating profile photo for user {self.userbot.user_id}: {e}")
            return False
