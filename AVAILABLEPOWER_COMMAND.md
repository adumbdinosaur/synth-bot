# /availablepower Command

## Overview
The `/availablepower` command allows users to quickly check their current energy status in any Telegram chat where their userbot is active.

## Usage
Simply type `/availablepower` in any chat and send the message. The bot will:
1. **Delete** your command message
2. **Replace** it with your current energy status

## Response Format
```
⚡ Energy Status ⚡
Power: 75/100 (75%)
[███████░░░]
Recharge Rate: 2 energy/minute
```

## Response Details

### Power Status
- **Current/Maximum**: Shows your current energy and maximum possible energy
- **Percentage**: Energy level as a percentage

### Visual Energy Bar
- **Filled segments (█)**: Represent available energy
- **Empty segments (░)**: Represent depleted energy
- **10 segments total**: Each segment represents 10% of your maximum energy

### Recharge Rate
- Shows how much energy you gain per minute
- Automatic energy regeneration rate

## Examples

### Full Energy (100/100)
```
⚡ Energy Status ⚡
Power: 100/100 (100%)
[██████████]
Recharge Rate: 1 energy/minute
```

### Half Energy (50/100)
```
⚡ Energy Status ⚡
Power: 50/100 (50%)
[█████░░░░░]
Recharge Rate: 1 energy/minute
```

### Low Energy (25/100)
```
⚡ Energy Status ⚡
Power: 25/100 (25%)
[██░░░░░░░░]
Recharge Rate: 3 energy/minute
```

### No Energy (0/100)
```
⚡ Energy Status ⚡
Power: 0/100 (0%)
[░░░░░░░░░░]
Recharge Rate: 1 energy/minute
```

## Privacy Features
- The original `/availablepower` command message is automatically deleted
- Only you can see your energy status (unless you use it in a public chat)
- No message content is logged for privacy

## Technical Details
- **Command Detection**: Case-insensitive (`/availablepower`, `/AVAILABLEPOWER`)
- **Energy Calculation**: Real-time energy with automatic recharge applied
- **Visual Bar**: 10-segment bar with Unicode block characters
- **Message Handling**: Automatic deletion and replacement
- **Error Handling**: Graceful handling of database errors

## Other Available Commands
- `/flip` - Random coin flip message
- `/beep` - Random beep sound message  
- `/dance` - Random dance move message

## Energy System Integration
The command integrates with the existing energy system:
- Reads from the same database as the web dashboard
- Shows real-time energy including automatic recharge
- Respects user-specific maximum energy and recharge rate settings
- No energy cost to check your status

## Use Cases
- **Quick Status Check**: Check energy before sending messages
- **Monitor Recharge**: See how fast your energy is regenerating
- **Energy Planning**: Plan message activities based on available energy
- **Troubleshooting**: Verify energy levels when experiencing limitations
