# Database Module Structure

This directory contains the modularized database operations for the Telegram UserBot.

## Structure

### Core Files
- `__init__.py` - Module exports and compatibility functions
- `base.py` - Base database manager with connection handling
- `manager.py` - Main database manager that combines all specialized managers

### Specialized Managers
- `user_manager.py` - User CRUD operations and admin management
- `energy_manager.py` - Energy system management (consumption, recharge, costs)
- `profile_manager.py` - Profile protection and original profile storage
- `badwords_manager.py` - Badword filtering and penalty management
- `session_manager.py` - Telegram session management
- `auth_manager.py` - Authentication and invite code management
- `autocorrect_manager.py` - Autocorrect settings and logging

## Usage

### Basic Usage
```python
from app.database import get_database_manager

db = get_database_manager()
user = await db.get_user_by_id(123)
energy_info = await db.get_user_energy(123)
```

### Using Specialized Managers Directly
```python
from app.database import get_database_manager

db = get_database_manager()

# Access specialized managers
user_data = await db.users.get_user_by_id(123)
energy_data = await db.energy.get_user_energy(123)
badwords = await db.badwords.get_user_badwords(123)
```

## Migration

The modular system maintains backward compatibility with the original `database_manager.py` through delegation methods. All existing code continues to work without changes.

### Key Benefits
1. **Modular Organization** - Related operations are grouped together
2. **Easier Maintenance** - Each manager handles a specific domain
3. **Better Testing** - Individual managers can be tested in isolation
4. **Cleaner Code** - Separation of concerns improves readability
5. **Backward Compatibility** - Existing code continues to work

### Database Tables

Each manager handles specific tables:

- **UserManager**: `users`
- **EnergyManager**: `users`, `messages`, `user_energy_costs`
- **ProfileManager**: `user_profile_protection`, `user_profile_revert_costs`
- **BadwordsManager**: `user_badwords`
- **SessionManager**: `telegram_sessions`
- **AuthManager**: `invite_codes`
- **AutocorrectManager**: `user_autocorrect_settings`

## Development

When adding new database operations:

1. Choose the appropriate specialized manager
2. Add the method to the manager class
3. Add a delegation method to `DatabaseManager` in `manager.py`
4. Update this README if needed

This structure makes the codebase more maintainable and easier to understand.
