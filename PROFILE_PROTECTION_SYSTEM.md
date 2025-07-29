# Profile Protection System

## Overview
The Profile Protection System is a security feature that prevents unauthorized changes to a user's Telegram profile while their userbot session is active. When enabled, any attempts to modify the profile name, bio, or profile photo will be automatically reverted and result in an energy penalty.

## Key Features

### 🔒 **Automatic Profile Locking**
- Profile is automatically locked when a userbot session starts
- Original profile data is stored securely in the database
- Profile is unlocked when the session ends

### 🔄 **Real-time Monitoring & Reversion**
- Monitors profile changes using Telegram's UserUpdate events
- Instantly reverts unauthorized changes to original values
- Works for first name, last name, bio, and profile photo

### ⚡ **Energy Penalties**
- Configurable energy penalty for each unauthorized change attempt
- Default penalty: 10 energy points (customizable 0-100)
- Penalties are applied even if user has insufficient energy
- Discourages repeated bypass attempts

### 🛡️ **Comprehensive Protection**
- **First Name**: Reverted to original value
- **Last Name**: Reverted to original value  
- **Bio (About)**: Reverted to original text
- **Profile Photo**: Removed if changed (original restoration planned)

## How It Works

### 1. Session Startup
```python
# When userbot session starts:
await self._store_original_profile()
```
- Current profile data is captured and stored
- Profile lock timestamp is recorded
- Protection becomes active

### 2. Profile Monitoring
```python
@self.client.on(events.UserUpdate)
async def profile_update_handler(event):
    await self._handle_profile_update(event)
```
- Listens for UserUpdate events
- Compares current profile with stored original
- Triggers reversion if changes detected

### 3. Change Detection & Reversion
```python
# For each detected change:
- Apply energy penalty
- Revert change to original value
- Log security event
```

### 4. Session Cleanup
```python
# When session ends:
await self.unlock_profile()
```
- Profile lock is cleared
- Protection becomes inactive
- User can freely modify profile

## Configuration

### Energy Penalty Settings
Users can configure the energy penalty through the web interface:

**Location**: Settings → Profile Protection  
**Range**: 0-100 energy points  
**Default**: 10 energy points

### Database Schema
```sql
CREATE TABLE user_profile_protection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    profile_change_penalty INTEGER DEFAULT 10,
    original_first_name TEXT,
    original_last_name TEXT,
    original_bio TEXT,
    original_profile_photo_id TEXT,
    profile_locked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    UNIQUE(user_id)
);
```

## API Endpoints

### GET /profile-protection
Display profile protection settings page
- Shows current penalty configuration
- Displays protection status (locked/unlocked)
- Shows original profile data if available

### POST /profile-protection
Update profile protection settings
- Updates energy penalty amount
- Validates penalty range (0-100)
- Redirects with success/error messages

## Implementation Details

### Profile Storage
```python
async def _store_original_profile(self):
    """Store user's original profile when session starts."""
    me = await self.client.get_me()
    await db_manager.store_original_profile(
        user_id=self.user_id,
        first_name=me.first_name,
        last_name=me.last_name,
        bio=getattr(me, 'about', None),
        profile_photo_id=str(me.photo.photo_id) if me.photo else None
    )
```

### Change Detection
```python
async def _handle_profile_update(self, event):
    """Detect and revert unauthorized profile changes."""
    # Get updated user data
    updated_user = await self.client.get_me()
    original_profile = await db_manager.get_original_profile(self.user_id)
    
    # Compare and detect changes
    changes_detected = []
    if updated_user.first_name != original_profile["first_name"]:
        changes_detected.append("first_name")
    # ... check other fields
    
    # Apply penalty and revert changes
    if changes_detected:
        await self._apply_energy_penalty()
        await self._revert_profile_changes(changes_detected)
```

### Profile Reversion
```python
async def _revert_profile_changes(self, revert_actions):
    """Revert profile changes to original values."""
    for field, original_value in revert_actions:
        if field == "first_name":
            await self.client.edit_profile(first_name=original_value or "")
        elif field == "last_name":
            await self.client.edit_profile(last_name=original_value or "")
        elif field == "bio":
            await self.client.edit_profile(about=original_value or "")
        elif field == "profile_photo":
            await self.client.edit_profile(photo=None)  # Remove changed photo
```

## Security Considerations

### 🔐 **Data Protection**
- Original profile data is stored securely in the database
- Only accessible when user is authenticated
- Automatically cleaned up when session ends

### 🚫 **Bypass Prevention**
- Energy penalties applied regardless of available energy
- Multiple change attempts result in multiple penalties
- No way to disable protection while session is active

### 📝 **Audit Trail**
- All protection events are logged with timestamps
- Energy penalty applications are tracked
- Profile change attempts are recorded

## Logging

The system provides comprehensive logging for security monitoring:

```
🔒 PROFILE LOCKED | User: username (ID: 12345) | Profile protection enabled
🚫 UNAUTHORIZED PROFILE CHANGES DETECTED | User: username (ID: 12345) | Changes: first_name: 'Original' -> 'Changed'
⚡ PROFILE CHANGE PENALTY | User: username (ID: 12345) | Applied 10 energy penalty (Energy: 90/100) | Changes reverted
🔓 PROFILE UNLOCKED | User: username (ID: 12345)
```

## Benefits

### 👤 **User Security**
- Protects against accidental profile changes
- Prevents unauthorized modifications during automation
- Maintains consistent identity while bot is active

### 🛡️ **System Integrity**
- Ensures profile data remains consistent
- Prevents confusion in chats and groups
- Maintains professional appearance

### ⚖️ **Fair Enforcement**
- Energy penalties discourage abuse
- Configurable penalties allow user control
- Automatic enforcement requires no manual intervention

## Future Enhancements

### 🔮 **Planned Features**
- **Photo Restoration**: Store and restore original profile photos
- **Partial Protection**: Allow specific fields to be modified
- **Scheduled Unlocks**: Temporary profile unlock periods
- **Admin Override**: Emergency unlock capabilities
- **Change Notifications**: Alert users of attempted changes

### 🧪 **Advanced Options**
- **Whitelist Changes**: Allow specific profile modifications
- **Time-based Penalties**: Increasing penalties for repeated attempts
- **Integration Alerts**: Notify external systems of security events

## Troubleshooting

### Common Issues

**Q: Profile changes not being detected**
- Ensure session is active and connected
- Check that UserUpdate events are being received
- Verify original profile data is stored

**Q: Reversion not working**
- Check Telegram client permissions
- Verify user has profile edit capabilities
- Review error logs for specific failures

**Q: Energy penalties not applied**
- Confirm energy system is functional
- Check database connectivity
- Verify penalty configuration is set

### Debug Commands
```python
# Check if profile is locked
is_locked = await db_manager.is_profile_locked(user_id)

# Get original profile data
original = await db_manager.get_original_profile(user_id) 

# Get current penalty setting
penalty = await db_manager.get_profile_change_penalty(user_id)
```

## Testing

The system includes comprehensive test suite:
```bash
python test_profile_protection_system.py
```

Tests cover:
- Database operations
- Profile storage and retrieval
- Energy penalty application
- Lock/unlock functionality
- Edge cases and error handling
