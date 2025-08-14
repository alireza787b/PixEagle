#!/usr/bin/env python3
"""
Test script to verify FastAPIHandler initialization fix
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_fastapi_handler_init():
    """Test if FastAPIHandler can be initialized without errors"""
    try:
        from classes.fastapi_handler import FastAPIHandler
        from classes.app_controller import AppController
        
        print("Testing FastAPIHandler initialization...")
        
        # Create a mock app controller (we'll just pass None for now)
        # This should not cause the asyncio error anymore
        handler = FastAPIHandler(None)
        print("✅ FastAPIHandler initialized successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing FastAPIHandler: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_fastapi_handler_init()
    sys.exit(0 if success else 1)

