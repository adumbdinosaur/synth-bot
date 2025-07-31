"""
Backward compatibility module for telegram_client.py

This module provides backward compatibility by importing the modular telegram client system.
The original monolithic telegram_client.py has been refactored into specialized handlers
but this module maintains the same API for existing code.

Original file backed up as: telegram_client.py.backup
"""

# Import the modular telegram client system
from app.telegram import (
    TelegramUserBot,
    TelegramClientManager,
    get_telegram_manager,
    initialize_telegram_manager,
    recover_telegram_sessions,
)

# Maintain backward compatibility - export the same classes and functions
__all__ = [
    "TelegramUserBot",
    "TelegramClientManager", 
    "get_telegram_manager",
    "initialize_telegram_manager",
    "recover_telegram_sessions",
]
