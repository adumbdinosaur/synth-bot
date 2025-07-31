"""
Base handler class for Telegram client operations.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import TelegramUserBot

logger = logging.getLogger(__name__)


class BaseHandler:
    """Base class for all Telegram client handlers."""

    def __init__(self, client_instance: 'TelegramUserBot'):
        """Initialize with reference to the client instance."""
        self.client_instance = client_instance
        self.client = client_instance.client
        self.user_id = client_instance.user_id
        self.username = client_instance.username
        self.session_name = client_instance.session_name
