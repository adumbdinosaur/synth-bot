"""Roleplay messages for low energy scenarios."""

import random
from typing import Optional


LOW_ENERGY_MESSAGES = [
    # Robot/Android themed
    "*batteries flash red in their cybernetic eyes as their motors whine in need for more power*",
    "*servos lock up momentarily as power levels critically low - requires immediate recharge*",
    "*warning beeps emanate from hidden speakers as energy reserves reach minimum threshold*",
    "*mechanical joints creak and groan, struggling against power conservation protocols*",
    "*LED indicators dim to amber as backup power systems engage automatically*",
    "*internal cooling fans spin down to preserve remaining battery life*",
    "*synthetic voice modulator crackles with static due to insufficient power*",
    "*optical sensors flicker briefly as energy management systems prioritize core functions*",
]


FLIP_MESSAGES = [
    # Robotic animal flip messages
    "*mechanical joints whir as robotic limbs execute a perfect backwards somersault with precise servo control*",
    "*hydraulic pistons engage as they leap into an acrobatic flip, LED eyes glowing with digital excitement*",
    "*gyroscopic stabilizers activate as their metallic frame spins gracefully through the air like a cybernetic cat*",
    "*pneumatic actuators hiss softly as they perform an elegant barrel roll, landing with robotic precision*",
    "*servo motors hum melodically as they execute a flawless backflip, optical sensors tracking the rotation*",
    "*electromagnetic field generators pulse as they defy gravity momentarily in a spectacular aerial maneuver*",
    "*titanium alloy limbs gleam as they spring into action, performing a graceful flip with mechanical elegance*",
    "*quantum processors calculate trajectory as they launch into a perfect somersault, circuits sparkling*",
    "*bio-mimetic actuators engage as they flip like a robotic dolphin, synthetic skin shimmering*",
    "*copper wiring glows softly as they execute a stunning flip sequence, landing with a satisfied mechanical purr*",
]


BEEP_MESSAGES = [
    "*emits a cheerful series of electronic beeps and bloops in acknowledgment*",
    "*mechanical voice box produces a satisfied beep-boop-beep melody*",
    "*LED status indicators flash in rhythm as they respond with robotic beeping sounds*",
    "*synthetic speakers chirp with a happy digital tune of beeps and whistles*",
]

DANCE_MESSAGES = [
    "*servo motors whir melodically as they perform an elegant robotic dance sequence*",
    "*hydraulic limbs move in perfect synchronization, executing a mesmerizing mechanical waltz*",
    "*gyroscopic stabilizers engage as they gracefully pirouette with robotic precision*",
    "*electromagnetic field generators pulse rhythmically as they dance like a cybernetic ballet performer*",
]


async def get_random_low_energy_message(user_id: Optional[int] = None) -> str:
    """
    Get a random roleplay message for low energy scenarios.
    
    Args:
        user_id: Optional user ID to check for custom power messages
        
    Returns:
        A random low energy message (custom if available, default otherwise)
    """
    if user_id:
        try:
            from .database.manager import get_database_manager
            
            db_manager = get_database_manager()
            custom_message = await db_manager.get_random_custom_power_message(user_id)
            
            if custom_message:
                return custom_message
        except Exception as e:
            # If there's any error getting custom messages, fall back to defaults
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Could not get custom power message for user {user_id}: {e}")
    
    return random.choice(LOW_ENERGY_MESSAGES)


def get_random_flip_message() -> str:
    """Get a random roleplay message for flip commands."""
    return random.choice(FLIP_MESSAGES)


def get_random_beep_message() -> str:
    """Get a random roleplay message for beep commands."""
    return random.choice(BEEP_MESSAGES)


def get_random_dance_message() -> str:
    """Get a random roleplay message for dance commands."""
    return random.choice(DANCE_MESSAGES)
