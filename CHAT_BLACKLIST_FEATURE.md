# Chat Blacklist Feature for Locked Sessions

## Overview
This feature allows users with locked profiles to create a blacklist of chats where message filtering (badwords and autocorrect) will not apply. This provides flexibility for users who want to maintain strict filtering in most contexts but need unrestricted communication in specific chats.

## Key Features

### 1. Profile Lock Requirement
- **Requirement**: Only users with locked profiles can access chat blacklist functionality
- **Rationale**: This ensures the feature is only available to users who have demonstrated commitment to profile protection
- **Implementation**: All routes check `is_profile_locked()` before allowing access

### 2. Chat-Specific Filtering Bypass
- **Functionality**: Messages sent to blacklisted chats bypass all content filtering
- **Scope**: Bypasses badwords filtering and autocorrect processing
- **Energy**: Energy costs still apply (only content filtering is bypassed)

### 3. User-Controlled Management
- **Location**: Accessible via user dashboard (System Config > Chat Blacklist)
- **Visibility**: Menu item only appears for users with locked profiles
- **Self-Service**: Users manage their own blacklists without admin intervention

## Technical Implementation

### Database Schema
```sql
CREATE TABLE IF NOT EXISTS user_chat_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    chat_title TEXT,
    chat_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE(user_id, chat_id)
);
```

### Message Processing Flow
1. **OOC Check**: Out-of-character messages bypass all filtering (existing)
2. **Blacklist Check**: If profile is locked AND chat is blacklisted → bypass all filtering
3. **Normal Processing**: Standard energy checks, badwords, and autocorrect apply

### Key Components
- **Database Manager**: `ChatBlacklistManager` for all database operations
- **Message Handler**: Updated to check blacklist before applying filters
- **Routes**: User-facing routes in `/chat-blacklist` endpoints
- **Template**: `chat_blacklist.html` for management interface

## User Interface

### Dashboard Integration
- **Menu Item**: "Chat Blacklist" appears in System Config dropdown
- **Conditional Display**: Only visible when `is_profile_locked` is true
- **Icon**: Shield icon to indicate protection/bypass functionality

### Management Interface
- **Add Chat**: Form to add chat ID, title, and type
- **Chat List**: Visual display of all blacklisted chats
- **Remove Chat**: One-click removal with confirmation
- **Validation**: Chat ID validation and error handling

### User Experience
- **Clear Requirements**: Prominent display of profile lock requirement
- **Helpful Information**: Instructions on finding chat IDs
- **Visual Feedback**: Success/error messages for all operations

## Security Considerations

### Access Control
- **Profile Lock Gate**: Only locked profiles can access the feature
- **User Isolation**: Users can only manage their own blacklists
- **No Admin Override**: Admin cannot manage user blacklists (user privacy)

### Data Validation
- **Chat ID Validation**: Non-zero integer validation
- **Input Sanitization**: Proper handling of optional fields
- **Unique Constraints**: Database prevents duplicate entries

## Use Cases

### Legitimate Scenarios
1. **Close Friends**: Private conversations with trusted individuals
2. **Professional**: Work-related communications requiring specific language
3. **Creative**: Roleplay or creative writing contexts
4. **Technical**: Programming or technical discussions with specific terminology

### Safeguards
- **Locked Profile Requirement**: Ensures user commitment to general protection
- **Chat-Specific**: Granular control rather than global bypass
- **Energy Costs**: Economic disincentive still applies

## Testing

### Automated Tests
- **Database Operations**: CRUD operations for blacklist management
- **Message Filtering**: Bypass logic verification
- **Access Control**: Profile lock requirement validation

### Manual Testing
- **UI Flow**: Dashboard integration and user experience
- **Edge Cases**: Invalid chat IDs, non-existent chats
- **Security**: Unauthorized access attempts

## Future Enhancements

### Potential Features
1. **Chat Discovery**: Integration with Telegram API to auto-populate chat info
2. **Time-Based**: Temporary blacklist entries with expiration
3. **Pattern Matching**: Blacklist by chat name patterns
4. **Audit Log**: Track blacklist changes for transparency

### Monitoring
- **Usage Analytics**: Track blacklist adoption and usage patterns
- **Performance**: Monitor impact on message processing speed
- **Abuse Detection**: Identify potential system abuse patterns

## Configuration

### Web Interface
- Routes: `/chat-blacklist/*` for user management
- Templates: `chat_blacklist.html` for the management interface
- Dashboard: Integration with existing user dashboard

### Database
- Automatic migration on application startup
- Indexes on user_id and chat_id for performance
- Cascade deletion when users are removed

## Conclusion

The Chat Blacklist feature provides a balanced approach to message filtering, offering flexibility for users with locked profiles while maintaining overall system integrity. The implementation prioritizes user privacy, security, and ease of use while providing the necessary controls to prevent abuse.

This feature enhances the user experience for committed users (those with locked profiles) without compromising the system's core filtering functionality or security model.
