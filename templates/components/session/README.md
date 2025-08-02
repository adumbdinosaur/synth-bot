# Session Info Components

This directory contains the components that make up the session info page, broken down from the original monolithic `session_info.html` template.

## Component Structure

### `/templates/components/session/`

The session info page has been decomposed into the following reusable components:

#### Core Components

1. **`header.html`** - Session header with user info, online status, and navigation
   - User display name and status badge
   - User ID display
   - Back to dashboard button

2. **`alerts.html`** - Success and error message display
   - Success/error alerts from query parameters
   - Auto-dismissible alerts

3. **`overview-cards.html`** - Session overview cards
   - Current energy display with progress bar
   - Energy recharge rate with inline editor
   - Member since date
   - Energy recharge rate info alert

#### Feature Components

4. **`energy-management.html`** - Energy management section
   - Current energy display with detailed progress
   - Energy action buttons (Add, Remove, Set, Max Energy)
   - Recharge rate configuration
   - Energy management guide

5. **`profile-management.html`** - Profile management section
   - Current vs original profile comparison
   - Profile update form (name, bio, photo)
   - Profile revert cost configuration
   - Profile management guide

6. **`energy-cost-config.html`** - Energy cost configuration
   - Message type energy costs configuration
   - Reset to defaults functionality
   - Dynamic message type icons

7. **`autocorrect-config.html`** - Autocorrect configuration
   - Enable/disable autocorrect toggle
   - Penalty per correction setting
   - Autocorrect information guide

8. **`badwords-management.html`** - Badwords management
   - Add new badwords form
   - Current badwords list with editing
   - Case sensitivity options
   - Badwords filtering guide

#### Support Components

9. **`info-section.html`** - Information section
   - Energy system explanation
   - Configuration tips and best practices

10. **`javascript.html`** - JavaScript functions
    - AJAX form handling
    - UI update functions
    - Collapsible section handlers
    - Alert management

## Usage

The main `session_info.html` template now simply includes these components:

```html
{% extends "base.html" %}

{% block title %}Session Info - {{ session.display_name }}{% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="row">
        <div class="col-md-12">
            <!-- Session Header -->
            {% include "components/session/header.html" %}

            <!-- Alert Messages -->
            {% include "components/session/alerts.html" %}

            <!-- Session Overview Cards -->
            {% include "components/session/overview-cards.html" %}

            <!-- Energy Management Section -->
            {% include "components/session/energy-management.html" %}

            <!-- Profile Management Section -->
            {% include "components/session/profile-management.html" %}

            <!-- Energy Cost Configuration -->
            {% include "components/session/energy-cost-config.html" %}

            <!-- Autocorrect Configuration Section -->
            {% include "components/session/autocorrect-config.html" %}

            <!-- Badwords Management Section -->
            {% include "components/session/badwords-management.html" %}

            <!-- Information Section -->
            {% include "components/session/info-section.html" %}
        </div>
    </div>
</div>

<!-- JavaScript Functions -->
{% include "components/session/javascript.html" %}
{% endblock %}
```

## Benefits

1. **Maintainability** - Each component is focused on a single responsibility
2. **Reusability** - Components can be reused in other pages if needed
3. **Readability** - Much easier to understand and navigate the codebase
4. **Testing** - Individual components can be tested in isolation
5. **Collaboration** - Multiple developers can work on different components simultaneously

## File Size Reduction

- **Original**: `session_info.html` was 1,345 lines
- **Refactored**: Main template is now just 37 lines with 10 focused components
- **Average component size**: ~135 lines each, much more manageable

## Next Steps

Consider further improvements:
- Create similar component structures for other large templates
- Add component-level documentation
- Implement component unit tests
- Consider creating a component library for shared UI elements
