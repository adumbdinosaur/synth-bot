"""
Modular Telegram Client System for UserBot

This module provides a clean, maintainable structure for managing Telegram userbot operations.
The system is divided into specialized handlers for different functional areas:

- AuthenticationHandler: Handles code sending, verification, and 2FA
- MessageHandler: Processes messages, energy consumption, badwords, autocorrect
- ProfileHandler: Manages profile protection and monitoring
- ConnectionHandler: Handles client connections and session management

The TelegramUserBot class coordinates these handlers, providing a clean API
while maintaining backward compatibility with existing code.
"""

from .telegram_userbot import TelegramUserBot
from .manager import (
    TelegramClientManager,
    get_telegram_manager,
    initialize_telegram_manager,
    recover_telegram_sessions,
)

# Handlers (for direct access if needed)
from .authentication_handler import AuthenticationHandler
from .message_handler import MessageHandler
from .profile_handler import ProfileHandler
from .connection_handler import ConnectionHandler

__all__ = [
    # Main classes
    "TelegramUserBot",
    "TelegramClientManager",
    # Manager functions
    "get_telegram_manager",
    "initialize_telegram_manager", 
    "recover_telegram_sessions",
    # Handlers (for advanced usage)
    "AuthenticationHandler",
    "MessageHandler", 
    "ProfileHandler",
    "ConnectionHandler",
]
