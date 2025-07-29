"""Roleplay messages for low energy scenarios."""

import random


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


def get_random_low_energy_message() -> str:
    """Get a random roleplay message for low energy scenarios."""
    return random.choice(LOW_ENERGY_MESSAGES)
