# Autocorrect Toggle Fix

## Problem
The autocorrect setting was always turning to `False` instead of enabling when the checkbox was checked.

## Root Cause
In `/mnt/projects/new-tg-user-bot/app/routes/public_api.py` line 505, the code was checking:

```python
enabled = "enabled" in form and form["enabled"] == "on"
```

However, the HTML checkbox in the template has:
```html
<input type="checkbox" name="enabled" value="true" />
```

When checked, HTML checkboxes send their `value` attribute ("true"), not "on".
When unchecked, the field is not included in the form data at all.

## Solution
Changed the checkbox handling logic from:
```python
enabled = "enabled" in form and form["enabled"] == "on"
```

To:
```python
enabled = "enabled" in form and form["enabled"] == "true"
```

## Testing
- ✅ When checkbox is checked: `enabled = True`
- ✅ When checkbox is unchecked: `enabled = False`
- ✅ No syntax errors introduced

## Files Modified
- `/mnt/projects/new-tg-user-bot/app/routes/public_api.py` - Fixed checkbox value comparison

The autocorrect enable/disable functionality should now work correctly.
