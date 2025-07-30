#!/usr/bin/env python3
"""
Demonstration script showing the difference between the old and new badword filtering behavior.
"""

import re


def old_badword_filter(badword, message, case_sensitive=True):
    """Old filtering method that causes partial matches."""
    if case_sensitive:
        if badword in message:
            return message.replace(badword, "<redacted>")
    else:
        if badword.lower() in message.lower():
            # Simple case-insensitive replacement
            import re
            pattern = re.compile(re.escape(badword), re.IGNORECASE)
            return pattern.sub("<redacted>", message)
    return message


def new_badword_filter(badword, message, case_sensitive=True):
    """New filtering method that only matches whole words."""
    escaped_word = re.escape(badword)
    pattern = rf'\b{escaped_word}\b'
    
    if case_sensitive:
        regex = re.compile(pattern)
    else:
        regex = re.compile(pattern, re.IGNORECASE)
    
    return regex.sub("<redacted>", message)


def demonstrate_fix():
    """Demonstrate the difference between old and new filtering."""
    
    test_cases = [
        {
            "badword": "no",
            "messages": [
                "I said no",
                "I know nothing",
                "knowledge is power", 
                "now is the time",
                "no way",
                "There's no chance"
            ]
        },
        {
            "badword": "hell", 
            "messages": [
                "go to hell",
                "hello world",
                "shell script",
                "hell yeah",
                "Michelle is nice"
            ]
        },
        {
            "badword": "test",
            "messages": [
                "this is a test",
                "testing 123",
                "protest march",
                "test passed",
                "fastest runner"
            ]
        }
    ]
    
    print("=" * 80)
    print("BADWORD FILTERING FIX DEMONSTRATION")
    print("=" * 80)
    print()
    
    for case in test_cases:
        badword = case["badword"]
        messages = case["messages"]
        
        print(f"🔍 TESTING BADWORD: '{badword}'")
        print("-" * 50)
        
        for message in messages:
            old_result = old_badword_filter(badword, message, case_sensitive=False)
            new_result = new_badword_filter(badword, message, case_sensitive=False)
            
            # Check if there's a difference
            different = old_result != new_result
            
            print(f"Original:  '{message}'")
            print(f"Old fix:   '{old_result}'" + (" ⚠️  INCORRECT" if different and old_result != message else ""))
            print(f"New fix:   '{new_result}'" + (" ✅ CORRECT" if different and new_result == message else ""))
            
            if different:
                if old_result != message and new_result == message:
                    print("           ^ Fixed: No longer incorrectly filtering partial matches")
                elif old_result == message and new_result != message:
                    print("           ^ Correctly filtering whole word matches")
            print()
        
        print()


if __name__ == "__main__":
    demonstrate_fix()
