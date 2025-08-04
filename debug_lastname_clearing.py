#!/usr/bin/env python3
"""
Debug script to test last name clearing specifically.
"""


def test_empty_string_handling():
    """Test the exact logic used in ProfileManager for empty string handling."""

    print("🧪 Testing ProfileManager logic for clearing last name:")
    print("=" * 60)

    # Simulate current profile
    current_profile = {
        "first_name": "John",
        "last_name": "Smith",  # Current last name
        "bio": "Test bio",
    }

    print(f"Current profile: {current_profile}")

    # Test case: User submits empty string to clear last name
    input_first_name = None  # Don't change first name
    input_last_name = ""  # Empty string to clear last name
    input_bio = None  # Don't change bio

    print(
        f"\nUser input: first_name={repr(input_first_name)}, last_name={repr(input_last_name)}, bio={repr(input_bio)}"
    )

    # This is the exact ProfileManager logic
    update_data = {
        "first_name": input_first_name
        if input_first_name is not None
        else current_profile.get("first_name", ""),
        "last_name": input_last_name
        if input_last_name is not None
        else current_profile.get("last_name", ""),
        "bio": input_bio if input_bio is not None else current_profile.get("bio", ""),
    }

    print(f"\nProfileManager update_data: {update_data}")
    print(f"UpdateProfileRequest will be called with:")
    print(f"  first_name='{update_data['first_name']}'")
    print(f"  last_name='{update_data['last_name']}'")
    print(f"  about='{update_data['bio']}'")

    # Check what empty string evaluates to
    empty_string = ""
    print(f"\nEmpty string checks:")
    print(f"  '{empty_string}' is not None: {empty_string is not None}")
    print(f"  '{empty_string}' == '': {empty_string == ''}")
    print(f"  bool('{empty_string}'): {bool(empty_string)}")
    print(f"  len('{empty_string}'): {len(empty_string)}")

    # Expected result
    expected_last_name = ""  # Should be empty string to clear
    actual_last_name = update_data["last_name"]

    if actual_last_name == expected_last_name:
        print(
            f"\n✅ SUCCESS: last_name will be set to empty string '{actual_last_name}'"
        )
    else:
        print(f"\n❌ FAIL: Expected '{expected_last_name}', got '{actual_last_name}'")


def test_potential_issues():
    """Test potential issues that could prevent clearing."""

    print("\n\n🔍 Checking potential issues:")
    print("=" * 60)

    # Test 1: Form data handling
    print("1. Form data scenarios:")
    form_scenarios = [
        ("Empty input field", ""),
        ("Space only", " "),
        ("Multiple spaces", "   "),
        ("Null-like strings", "null"),
        ("None string", "None"),
    ]

    for desc, value in form_scenarios:
        print(
            f"   {desc}: '{value}' -> is_not_none: {value is not None}, bool: {bool(value)}"
        )

    # Test 2: String comparison edge cases
    print("\n2. String comparison edge cases:")
    test_strings = ["", " ", None, "None", "null", 0, False]

    for test_val in test_strings:
        is_not_none = test_val is not None
        would_use_current = not is_not_none
        print(
            f"   {repr(test_val)} -> is_not_None: {is_not_none}, would_use_current: {would_use_current}"
        )


if __name__ == "__main__":
    test_empty_string_handling()
    test_potential_issues()

    print("\n\n💡 Analysis:")
    print("=" * 60)
    print("The ProfileManager logic should work correctly for clearing last names.")
    print("If it's not working, the issue might be:")
    print("1. Form is not sending empty string (sending None instead)")
    print("2. JavaScript is modifying the value before sending")
    print("3. Telegram API is rejecting empty string for last_name")
    print("4. There's another code path being used")
    print("5. The profile is being reverted/restored after update")
