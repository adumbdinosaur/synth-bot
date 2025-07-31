"""
Message handler for Telegram userbot.
Handles incoming and outgoing message processing, energy consumption, badwords filtering, and autocorrect.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from telethon import events
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class MessageHandler(BaseHandler):
    """Handles message-related operations for Telegram userbot."""

    def __init__(self, userbot):
        super().__init__(userbot)
        self._message_handler_registered = False

    async def register_handlers(self):
        """Register message event handlers."""
        if not self.userbot.client or self._message_handler_registered:
            return False

        try:

            @self.userbot.client.on(events.NewMessage(outgoing=True))
            async def outgoing_message_handler(event):
                await self._handle_outgoing_message(event)

            @self.userbot.client.on(events.NewMessage(incoming=True))
            async def incoming_message_handler(event):
                await self._handle_incoming_message(event)

            self._message_handler_registered = True
            logger.info(
                f"Message handlers registered for user {self.userbot.user_id} ({self.userbot.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to register message handlers for user {self.userbot.user_id}: {e}"
            )
            return False

    async def _handle_outgoing_message(self, event):
        """Handle outgoing message event."""
        try:
            from ..database import get_database_manager

            db_manager = get_database_manager()
            message_text = event.message.text or ""

            # Check if this is a special message by content FIRST
            special_message_type = self._is_special_message(message_text)

            # Determine energy cost message type
            energy_message_type = self._get_message_type(event.message)

            # Get energy cost for this message type
            energy_cost = await db_manager.get_message_energy_cost(
                self.userbot.user_id, energy_message_type
            )

            # Get current energy level BEFORE any processing
            energy_info = await db_manager.get_user_energy(self.userbot.user_id)
            current_energy = energy_info["energy"]

            # Check if user has sufficient energy BEFORE trying to consume it
            has_sufficient_energy = current_energy >= energy_cost

            # OUT-OF-ENERGY CHECK TAKES PRECEDENCE: If this is NOT a special message and user has insufficient energy, replace it
            if not special_message_type and not has_sufficient_energy:
                await self._replace_with_low_energy_message(event)
                return

            # If we reach here, user has sufficient energy OR it's a special message
            # Now check for badwords (only for text messages)
            badword_violations = None

            if message_text:
                # Handle badwords filtering
                badword_violations = await self._process_badwords(
                    event, message_text, db_manager
                )
                if badword_violations:
                    message_text = badword_violations["filtered_message"]

                # Handle autocorrect
                await self._process_autocorrect(event, message_text, db_manager)

            # Always try to consume base energy cost for the message
            consume_result = await db_manager.consume_user_energy(
                self.userbot.user_id, energy_cost
            )

            if consume_result["success"]:
                new_energy = consume_result["energy"]
                # Get max energy for proper logging
                energy_info = await db_manager.get_user_energy(self.userbot.user_id)
                max_energy = energy_info["max_energy"]
                
                logger.info(
                    f"⚡ ENERGY CONSUMED | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                    f"Message type: {energy_message_type} (cost: {energy_cost}) | "
                    f"Energy: {new_energy}/{max_energy} (-{energy_cost}) | "
                    f"Special: {special_message_type or 'None'}"
                )
            else:
                logger.warning(
                    f"⚡ ENERGY CONSUMPTION FAILED | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                    f"Required: {energy_cost}, Available: {current_energy}"
                )

            # Apply badword penalties if violations were found
            if badword_violations:
                await self._apply_badword_penalties(badword_violations)

            # Log message details (content excluded for privacy)
            await self._log_message_details(event, message_text, special_message_type)

        except Exception as e:
            logger.error(
                f"Error handling message for user {self.userbot.user_id} ({self.userbot.username}): {e}"
            )

    async def _handle_incoming_message(self, event):
        """Handle incoming message events for easter eggs and commands."""
        try:
            # Check if the message is a text message
            if not event.message.text:
                return

            message_text = event.message.text.strip().lower()

            # Check for easter egg commands
            response_msg = None
            command_type = None

            if message_text == "/flip":
                from ..roleplay_messages import get_random_flip_message

                response_msg = get_random_flip_message()
                command_type = "FLIP"
            elif message_text == "/beep":
                from ..roleplay_messages import get_random_beep_message

                response_msg = get_random_beep_message()
                command_type = "BEEP"
            elif message_text == "/dance":
                from ..roleplay_messages import get_random_dance_message

                response_msg = get_random_dance_message()
                command_type = "DANCE"
            elif message_text == "/availablepower":
                await self._handle_power_status_command(event)
                return  # Early return since we handle message deletion ourselves

            # If we have a response, send it
            if response_msg:
                # Send the easter egg response - these should consume energy
                await self.userbot.client.send_message(
                    event.chat_id, f"*{response_msg}*"
                )

                logger.info(
                    f"🎪 {command_type} EASTER EGG | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                    f"Responded to /{command_type.lower()} command with: {response_msg[:50]}..."
                )

        except Exception as e:
            logger.error(
                f"Error handling incoming message for user {self.userbot.user_id} ({self.userbot.username}): {e}"
            )

    async def _handle_power_status_command(self, event):
        """Handle /availablepower command."""
        try:
            from ..database import get_database_manager

            db_manager = get_database_manager()
            energy_info = await db_manager.get_user_energy(self.userbot.user_id)

            current_energy = energy_info["energy"]
            max_energy = energy_info["max_energy"]
            recharge_rate = energy_info["recharge_rate"]

            # Create energy status message
            energy_percentage = int((current_energy / max_energy) * 100)

            # Create energy bar visualization
            bar_length = 10
            filled_bars = int((current_energy / max_energy) * bar_length)
            energy_bar = "█" * filled_bars + "░" * (bar_length - filled_bars)

            response_msg = (
                f"⚡ Energy Status ⚡\n"
                f"Power: {current_energy}/{max_energy} ({energy_percentage}%)\n"
                f"[{energy_bar}]\n"
                f"Recharge Rate: {recharge_rate} energy/minute"
            )

            # Delete the original command message and send the response
            await self.userbot.client.delete_messages(event.chat_id, event.message.id)
            await self.userbot.client.send_message(event.chat_id, response_msg)

            logger.info(
                f"⚡ POWER STATUS | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                f"Energy: {current_energy}/{max_energy} | Recharge: {recharge_rate}/min"
            )

        except Exception as e:
            logger.error(
                f"Error handling power status command for user {self.userbot.user_id}: {e}"
            )

    async def _process_badwords(
        self, event, message_text: str, db_manager
    ) -> Optional[Dict[str, Any]]:
        """Process badwords filtering for a message."""
        filter_result = await db_manager.filter_badwords_from_message(
            self.userbot.user_id, message_text
        )

        # If badwords found, handle them
        if filter_result["has_violations"]:
            # Replace the message with filtered version
            await self.userbot.client.delete_messages(event.chat_id, event.message.id)
            await self.userbot.client.send_message(
                event.chat_id, filter_result["filtered_message"]
            )
            return filter_result

        return None

    async def _process_autocorrect(
        self, event, message_text: str, db_manager
    ) -> Optional[Dict[str, Any]]:
        """Process autocorrect for a message."""
        # Check autocorrect settings and apply if enabled
        autocorrect_settings = await db_manager.get_autocorrect_settings(
            self.userbot.user_id
        )
        if not autocorrect_settings["enabled"] or not message_text:
            return None

        try:
            from ..autocorrect import get_autocorrect_manager

            autocorrect_manager = get_autocorrect_manager()
            autocorrect_result = await autocorrect_manager.correct_spelling(
                message_text
            )

            # If corrections were made, edit the message and apply penalty
            if autocorrect_result["count"] > 0:
                corrected_text = autocorrect_result["sentence"]
                penalty = (
                    autocorrect_result["count"]
                    * autocorrect_settings["penalty_per_correction"]
                )

                # Edit the message with corrected text
                try:
                    await self.userbot.client.delete_messages(
                        event.chat_id, event.message.id
                    )
                    await self.userbot.client.send_message(
                        event.chat_id, corrected_text
                    )

                    # Apply penalty
                    await db_manager.consume_user_energy(self.userbot.user_id, penalty)

                    # Log the autocorrection
                    await db_manager.log_autocorrect_usage(
                        self.userbot.user_id,
                        message_text,
                        corrected_text,
                        autocorrect_result["count"],
                    )

                    logger.info(
                        f"📝 AUTOCORRECT | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                        f"Corrections: {autocorrect_result['count']} | Penalty: {penalty} | "
                        f"Original: '{message_text[:50]}...' -> Corrected: '{corrected_text[:50]}...'"
                    )
                except Exception as e:
                    logger.error(
                        f"Error applying autocorrect for user {self.userbot.user_id}: {e}"
                    )

            return autocorrect_result

        except Exception as e:
            logger.error(
                f"Error in autocorrect processing for user {self.userbot.user_id}: {e}"
            )
            return None

    async def _apply_badword_penalties(self, filter_result: Dict[str, Any]):
        """Apply energy penalties for badword violations."""
        try:
            from ..database import get_database_manager

            db_manager = get_database_manager()

            violations = filter_result["violations"]
            total_penalty = filter_result["total_penalty"]
            violated_words = [violation["word"] for violation in violations]

            # Apply energy penalty
            penalty_result = await db_manager.consume_user_energy(
                self.userbot.user_id, total_penalty
            )

            # Get max energy for proper logging
            energy_info = await db_manager.get_user_energy(self.userbot.user_id)
            max_energy = energy_info["max_energy"]

            # Log the violation
            violation_log = f"Badwords detected: {', '.join(violated_words)} | Total penalty: {total_penalty}"
            if penalty_result["success"]:
                violation_log += (
                    f" | Energy: {penalty_result['energy']}/{max_energy} (-{total_penalty})"
                )
            else:
                violation_log += f" | Insufficient energy: {penalty_result.get('current_energy', 0)}/{max_energy}"

            logger.warning(
                f"🚫 BADWORD VIOLATION | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                f"{violation_log} | Badwords replaced with <redacted>"
            )

        except Exception as e:
            logger.error(
                f"Error applying badword penalties for user {self.userbot.user_id}: {e}"
            )

    async def _replace_with_low_energy_message(self, event):
        """Replace the original message with a low energy roleplay message."""
        try:
            from ..roleplay_messages import get_random_low_energy_message

            # Get a random low energy message
            low_energy_msg = get_random_low_energy_message()

            # Delete the original message
            await self.userbot.client.delete_messages(event.chat_id, event.message.id)

            # Send the low energy replacement message
            await self.userbot.client.send_message(event.chat_id, f"*{low_energy_msg}*")

            logger.info(
                f"🔋 LOW ENERGY REPLACEMENT | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                f"Original deleted, sent: {low_energy_msg[:50]}..."
            )

        except Exception as e:
            logger.error(
                f"Error replacing message with low energy version for user {self.userbot.user_id}: {e}"
            )

    async def _log_message_details(
        self, event, message_text: str, special_message_type: Optional[str]
    ):
        """Log message details for monitoring."""
        try:
            # Get chat information for logging
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", getattr(chat, "first_name", "Unknown"))
            chat_type = (
                "channel"
                if hasattr(chat, "broadcast") and chat.broadcast
                else "group"
                if hasattr(chat, "megagroup") and chat.megagroup
                else "private"
            )

            # Log message details (content excluded for privacy)
            logger.info(
                f"📤 MESSAGE SENT | User: {self.userbot.username} (ID: {self.userbot.user_id}) | "
                f"Chat: {chat_title} ({chat_type}) | "
                f"Length: {len(message_text)} chars | "
                f"Special: {special_message_type or 'None'} | "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(
                f"Error logging message details for user {self.userbot.user_id}: {e}"
            )

    def _get_message_type(self, message) -> str:
        """Determine the message type for energy cost calculation."""
        if not message:
            return "text"

        # Check for different media types based on Telethon message attributes
        if hasattr(message, "media") and message.media:
            return self._parse_media_type(message)

        # Check for grouped media (media group/album)
        if hasattr(message, "grouped_id") and message.grouped_id:
            return "media_group"

        # Default to text message
        return "text"

    def _parse_media_type(self, message) -> str:
        """Parse media type from message."""
        media_type = type(message.media).__name__

        if "Photo" in media_type:
            return "photo"
        elif "Document" in media_type:
            return self._parse_document_type(message)
        elif "Game" in media_type:
            return "game"
        elif "Poll" in media_type:
            return "poll"
        elif "Contact" in media_type:
            return "contact"
        elif "GeoPoint" in media_type or "Geo" in media_type:
            return "location"
        elif "Venue" in media_type:
            return "venue"
        elif "WebPage" in media_type:
            return "web_page"
        elif "MessageMediaDocument" in media_type:
            # Handle stickers specifically
            if hasattr(message.media, "document") and hasattr(
                message.media.document, "attributes"
            ):
                for attr in message.media.document.attributes:
                    if "DocumentAttributeSticker" in type(attr).__name__:
                        return "sticker"
            return "document"

        return "document"

    def _parse_document_type(self, message) -> str:
        """Parse document-specific media types."""
        if not hasattr(message.media, "document"):
            return "document"

        doc = message.media.document
        if not hasattr(doc, "mime_type"):
            return "document"

        mime = doc.mime_type
        if mime.startswith("video/"):
            # Check if it's a GIF/animation
            if hasattr(doc, "attributes"):
                for attr in doc.attributes:
                    attr_type = type(attr).__name__
                    if "DocumentAttributeAnimated" in attr_type:
                        return "gif"
                    elif (
                        "DocumentAttributeVideo" in attr_type
                        and hasattr(attr, "round_message")
                        and attr.round_message
                    ):
                        return "video"  # Video note
            return "video"
        elif mime.startswith("audio/"):
            # Check if it's a voice message
            if hasattr(doc, "attributes"):
                for attr in doc.attributes:
                    if (
                        "DocumentAttributeAudio" in type(attr).__name__
                        and hasattr(attr, "voice")
                        and attr.voice
                    ):
                        return "voice"
            return "audio"
        elif mime.startswith("image/") and "gif" in mime:
            return "gif"

        return "document"

    def _is_special_message(self, message_text: str) -> Optional[str]:
        """Identify if a message is a special message by its content. Returns message type or None."""
        if not message_text:
            return None

        # Import here to avoid circular imports
        from ..roleplay_messages import (
            LOW_ENERGY_MESSAGES,
            FLIP_MESSAGES,
            BEEP_MESSAGES,
            DANCE_MESSAGES,
        )

        # Remove any emoji prefix and asterisks for comparison
        clean_text = message_text.strip()
        if clean_text.startswith("🎭 "):
            clean_text = clean_text[3:].strip()

        # Remove asterisks for roleplay message comparison
        clean_text_no_asterisks = clean_text.strip("*").strip()

        # Check against different message types
        message_sets = [
            (LOW_ENERGY_MESSAGES, "low_energy"),
            (FLIP_MESSAGES, "flip"),
            (BEEP_MESSAGES, "beep"),
            (DANCE_MESSAGES, "dance"),
        ]

        for message_set, message_type in message_sets:
            for special_msg in message_set:
                if clean_text_no_asterisks == special_msg.strip("*").strip():
                    return message_type

        return None
