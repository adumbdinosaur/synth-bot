# Custom Redactions Feature

This feature allows controllers to specify custom word replacements with energy penalties for specific users. It's managed through the session info page and automatically processes messages.

## Features

### 1. User-Specific Redactions
- Each redaction applies only to one user
- Controllers can set different redactions for different users
- Original word → Replacement word mapping

### 2. Energy Penalties
- Configurable penalty per redaction (1-100 energy points)
- Penalty applied each time the word is found and replaced
- Multiple occurrences in one message apply penalty for each

### 3. Case Sensitivity Options
- Can be configured per redaction
- Case sensitive: "Word" ≠ "word"
- Case insensitive: "Word" = "word" (default)

### 4. Real-time Processing
- Messages are automatically processed before sending
- Original word is replaced with specified replacement
- Energy penalty is immediately applied
- Works alongside badwords filtering and autocorrect

## How It Works

### Message Processing Flow
1. User sends a message
2. **Badwords filtering** (replaces badwords with `<redacted>`)
3. **Custom redactions** (replaces specified words with custom replacements)
4. **Autocorrect** (fixes spelling if enabled)
5. Message is sent with all modifications

### Database Schema
```sql
CREATE TABLE user_custom_redactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    original_word TEXT NOT NULL,
    replacement_word TEXT NOT NULL,
    penalty INTEGER NOT NULL DEFAULT 5,
    case_sensitive BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE(user_id, original_word)
);
```

## Usage

### Adding Custom Redactions
1. Go to a user's session info page
2. Find the "Custom Redactions" section
3. Fill in:
   - **Original Word**: The word to be replaced
   - **Replacement Word**: What to replace it with
   - **Penalty**: Energy cost (1-100)
   - **Case Sensitive**: Whether matching should be exact case
4. Click "Add"

### Managing Redactions
- **Edit**: Click the edit button to modify replacement word or penalty
- **Remove**: Click the trash button to delete a redaction
- **View Statistics**: See total redactions and potential penalty

### API Endpoints
- `POST /api/sessions/{user_id}/custom_redactions` - Add redaction
- `PUT /api/sessions/{user_id}/custom_redactions/{original_word}` - Update redaction
- `DELETE /api/sessions/{user_id}/custom_redactions/{original_word}` - Remove redaction
- `GET /api/sessions/{user_id}/custom_redactions` - Get all redactions

## Examples

### Example 1: Language Filtering
- **Original Word**: "damn"
- **Replacement Word**: "darn"
- **Penalty**: 3 energy points
- **Case Sensitive**: No

Message: "This is damn frustrating!" → "This is darn frustrating!"
Energy: -3 points

### Example 2: Name Replacement
- **Original Word**: "John"
- **Replacement Word**: "J***"
- **Penalty**: 5 energy points
- **Case Sensitive**: Yes

Message: "John is here but john is not" → "J*** is here but john is not"
Energy: -5 points (only "John" with capital J is replaced)

### Example 3: Multiple Occurrences
- **Original Word**: "bad"
- **Replacement Word**: "not good"
- **Penalty**: 2 energy points
- **Case Sensitive**: No

Message: "This is bad, really bad!" → "This is not good, really not good!"
Energy: -4 points (2 occurrences × 2 penalty each)

## Technical Implementation

### Message Handler Integration
The custom redactions are processed in `MessageHandler._process_custom_redactions()` which:
1. Retrieves user's custom redactions from database
2. Uses regex matching to find words (with word boundaries)
3. Replaces found words with specified replacements
4. Applies energy penalty for each replacement
5. Updates the message content
6. Logs the redaction activity

### Database Managers
- `CustomRedactionsManager`: Handles database operations
- `DatabaseManager`: Provides unified access via main manager
- Integrated with existing energy penalty system

### Frontend Components
- **Template**: `templates/components/session/custom-redactions.html`
- **JavaScript**: Functions in `templates/components/session/javascript.html`
- **API Routes**: `app/routes/public_api.py`

## Migration

For existing installations, run the migration script:
```bash
python3 migrate_custom_redactions.py
```

This creates the `user_custom_redactions` table if it doesn't exist.

## Security & Performance

### Security
- User-specific redactions (no cross-user access)
- Input validation on word length and penalty values
- SQL injection protection via parameterized queries
- Authentication required for all API endpoints

### Performance
- Efficient regex matching with word boundaries
- Database indexes on user_id and original_word
- Minimal processing overhead (only when redactions exist)
- Processed after badwords but before autocorrect

## Future Enhancements

Potential improvements:
1. **Regex Patterns**: Support for regex patterns in original words
2. **Global Redactions**: System-wide redactions that apply to all users
3. **Time-based Redactions**: Redactions that expire after a certain time
4. **Import/Export**: Bulk management of redactions
5. **Statistics**: Detailed usage statistics and most-triggered redactions
