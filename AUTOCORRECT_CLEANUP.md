# Autocorrect Database Cleanup

This system automatically cleans up duplicate autocorrect settings entries during application startup.

## How It Works

1. **Automatic Startup Cleanup**: Every time the application starts, it automatically removes duplicate autocorrect settings, keeping only the most recent entry per user.

2. **Manual Cleanup Script**: You can also run the cleanup manually using the standalone script.

## Usage

### Automatic Cleanup (Recommended)
The cleanup runs automatically during application startup. No action needed.

### Manual Cleanup
Run the standalone cleanup script:
```bash
# Make sure you're in the project root directory
python cleanup_autocorrect.py

# Or using nix-shell
nix-shell --run "python cleanup_autocorrect.py"
```

## What Gets Cleaned

- **Target**: `user_autocorrect_settings` table
- **Logic**: For each user, keeps only the most recent record (by `created_at` timestamp, then by `id`)
- **Safety**: Never removes the last remaining record for a user

## Logging

- Cleanup operations are logged to both console and `cleanup.log` file
- Application startup logs show cleanup results
- Both success and error cases are logged

## Example Output

```
2025-07-31 06:22:26 - app.config - INFO - Running database cleanup operations...
2025-07-31 06:22:26 - app.database.autocorrect_manager - INFO - 🔄 Found 2 users with duplicate autocorrect settings (2 total duplicates)
2025-07-31 06:22:26 - app.database.autocorrect_manager - INFO - ✅ Cleaned up 2 duplicate autocorrect settings entries
2025-07-31 06:22:26 - app.config - INFO - 🗑️ Removed 2 duplicate autocorrect entries
2025-07-31 06:22:26 - app.config - INFO - ✅ Database cleanup completed
```

## Files Modified

- `app/database/autocorrect_manager.py` - Added `cleanup_duplicate_settings()` method
- `app/config.py` - Added `cleanup_database()` function and integrated into startup
- `cleanup_autocorrect.py` - Standalone cleanup script

## Safety Features

- **Non-destructive**: Only removes duplicates, never the last record for a user
- **Error handling**: Startup continues even if cleanup fails
- **Logging**: All operations are logged for audit purposes
- **Verification**: Script includes verification step to ensure cleanup was successful
