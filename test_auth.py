#!/usr/bin/env python3
"""
Test script for the authentication system
"""

import sys
import os

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, register_user, get_user_by_email, get_user_by_username

def test_database_setup():
    """Test database initialization"""
    print("Testing database setup...")
    try:
        init_db()
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def test_user_registration():
    """Test user registration"""
    print("\nTesting user registration...")
    try:
        user_id = register_user("testuser", "test@example.com", "password123", "Test Signature")
        if user_id:
            print(f"✅ User registered successfully with ID: {user_id}")
            return True
        else:
            print("❌ User registration failed")
            return False
    except Exception as e:
        print(f"❌ User registration failed with error: {e}")
        return False

def test_user_lookup():
    """Test user lookup functions"""
    print("\nTesting user lookup...")
    try:
        # Test get_user_by_email
        user = get_user_by_email("test@example.com")
        if user:
            print(f"✅ User found by email: {user['username']}")
        else:
            print("❌ User not found by email")
            return False
            
        # Test get_user_by_username
        user = get_user_by_username("testuser")
        if user:
            print(f"✅ User found by username: {user['email']}")
            return True
        else:
            print("❌ User not found by username")
            return False
    except Exception as e:
        print(f"❌ User lookup failed with error: {e}")
        return False

def main():
    """Main test function"""
    print("Running Authentication System Tests")
    print("=" * 40)
    
    tests = [
        test_database_setup,
        test_user_registration,
        test_user_lookup
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 40)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())