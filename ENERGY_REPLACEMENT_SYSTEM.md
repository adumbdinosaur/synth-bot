# Energy Replacement System Implementation

## Overview
The Telegram userbot now features an intelligent energy replacement system that:
- Monitors outgoing messages for energy consumption
- Identifies special messages by their content (not prefixes) 
- Automatically replaces insufficient energy messages with low energy roleplay responses
- Always consumes energy for special messages regardless of availability

## Key Features

### 1. Content-Based Message Identification
Messages are identified as special by matching their content against predefined message arrays:
- **Low Energy Messages**: Robotic/android themed messages about low power
- **Flip Messages**: Mechanical/robotic flip descriptions
- **Beep Messages**: Electronic beep sounds and responses  
- **Dance Messages**: Robotic dance sequences

### 2. Smart Energy Replacement Logic
```
For each outgoing message:
1. Check if message is special (by content matching)
2. Get energy cost for message type
3. Check if user has sufficient energy

If special message:
    - Always consume energy (even if insufficient)
    - Never replace message
    
If normal message:
    - If sufficient energy: consume energy normally
    - If insufficient energy: delete message and replace with low energy roleplay
```

### 3. Automatic Message Replacement
When a user sends a message but lacks sufficient energy:
1. Original message is deleted immediately
2. A random low energy roleplay message is sent instead
3. Energy is consumed for the replacement message
4. The replacement message is identified as special to prevent recursive replacement

## Implementation Details

### Message Identification Function
```python
def _is_special_message(self, message_text: str) -> str:
    """Identify if a message is a special message by its content."""
    # Handles emoji prefixes (🎭) and asterisks (*message*)
    # Returns: "low_energy", "flip", "beep", "dance", or None
```

### Updated Outgoing Message Handler
```python
async def _handle_outgoing_message(self, event):
    # 1. Identify special message type by content
    # 2. Check energy availability
    # 3. Apply replacement logic or consume energy
    # 4. Log actions with detailed information
```

### Message Replacement Function
```python
async def _replace_with_low_energy_message(self, event):
    # 1. Delete original message
    # 2. Send random low energy roleplay message
    # 3. Log the replacement action
```

## Message Format Examples

### Low Energy Messages
```
*batteries flash red in their cybernetic eyes as their motors whine in need for more power*
*servos lock up momentarily as power levels critically low - requires immediate recharge*
*warning beeps emanate from hidden speakers as energy reserves reach minimum threshold*
```

### Easter Egg Responses

#### Flip Command (`/flip`)
```
*mechanical joints whir as robotic limbs execute a perfect backwards somersault with precise servo control*
*hydraulic pistons engage as they leap into an acrobatic flip, LED eyes glowing with digital excitement*
```

#### Beep Command (`/beep`)
```
*emits a cheerful series of electronic beeps and bloops in acknowledgment*
*mechanical voice box produces a satisfied beep-boop-beep melody*
```

#### Dance Command (`/dance`)
```
*servo motors whir melodically as they perform an elegant robotic dance sequence*
*hydraulic limbs move in perfect synchronization, executing a mesmerizing mechanical waltz*
```

## Energy Consumption Rules

1. **Normal Messages**: Consume energy based on message type (text, photo, sticker, etc.)
2. **Special Messages**: Always consume energy, even if insufficient
3. **Insufficient Energy**: Replace normal messages with low energy roleplay
4. **No Exemptions**: All special messages (including low energy replacements) consume energy

## Logging and Monitoring

The system provides detailed logging:
- Energy consumption with before/after levels
- Message type identification
- Replacement actions
- Special message detection
- Error handling and recovery

### Example Log Output
```
⚡ ENERGY CONSUMED | User: test_user (ID: 12345) | Message type: text (cost: 5) | Energy: 15/100 (-5) | Special: None
🔋 LOW ENERGY REPLACEMENT | User: test_user (ID: 12345) | Original deleted, sent: batteries flash red in their cybernetic eyes...
📤 MESSAGE SENT | User: test_user (ID: 12345) | Chat: Test Chat (private) | Special: low_energy
```

## Testing

The implementation includes comprehensive tests:
- Content-based message identification verification
- Energy replacement logic simulation  
- Special message handling scenarios
- Edge cases and error conditions

All tests pass successfully, confirming the system works as designed.

## Benefits

1. **Seamless User Experience**: Users don't need to check energy before sending
2. **Immersive Roleplay**: Low energy messages maintain character consistency
3. **Fair Energy System**: No way to bypass energy costs
4. **Robust Identification**: Content-based matching prevents gaming the system
5. **Comprehensive Logging**: Full audit trail of all energy actions
