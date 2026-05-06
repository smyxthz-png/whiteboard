#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify RunningHub Image Generation API key is valid
"""

import os
import sys
import io
import requests
import time

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def load_env():
    """Load .env file from skills/whiteboard-video-workflow"""
    env_path = os.path.join(os.path.dirname(__file__), '../../skills/whiteboard-video-workflow/.env')
    env_vars = {}

    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()

    return env_vars

def test_image_api():
    """Test Image Generation API with a simple request"""
    print("=" * 60)
    print("RunningHub Image Generation API Key Test")
    print("=" * 60)

    # Load env
    env_vars = load_env()

    # Get API key
    api_key = env_vars.get('RUNNINGHUB_API_KEY')

    if not api_key:
        print("[ERROR] No valid API key found in .env")
        print("[ERROR] Please set RUNNINGHUB_API_KEY in skills/whiteboard-video-workflow/.env")
        return False

    print(f"[INFO] Testing API Key: {api_key[:8]}...{api_key[-4:]}")

    # Test prompt
    test_prompt = "a simple red circle on white background"
    print(f"[INFO] Test Prompt: {test_prompt}")

    # RunningHub Image Generation endpoint
    submit_url = "https://www.runninghub.cn/openapi/v2/rhart-image-n-g31-flash/text-to-image"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Build simple request
    payload = {
        "prompt": test_prompt,
        "aspectRatio": "16:9",
        "resolution": "2k"
    }

    # Submit task
    print("\n[TEST] Submitting image generation task...")
    try:
        response = requests.post(submit_url, headers=headers, json=payload, timeout=30)

        print(f"[INFO] HTTP Status: {response.status_code}")

        if response.status_code == 401:
            print("[ERROR] ❌ Authentication failed - API key is invalid")
            return False

        if response.status_code == 403:
            print("[ERROR] ❌ Access forbidden - API key may not have permissions")
            return False

        response.raise_for_status()
        result = response.json()

        print(f"[INFO] Response: {result}")

        if result.get('taskId'):
            print(f"[SUCCESS] ✅ Task submitted successfully!")
            print(f"[INFO] Task ID: {result.get('taskId')}")
            print("\n" + "=" * 60)
            print("✅ API KEY IS VALID AND WORKING!")
            print("=" * 60)
            return True
        else:
            print(f"[ERROR] ❌ Task submission failed: {result}")
            return False

    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] ❌ HTTP Error {e.response.status_code}")
        print(f"[ERROR] Response: {e.response.text}")
        return False
    except requests.exceptions.Timeout:
        print(f"[ERROR] ❌ Request timeout - check network connection")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] ❌ Network error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] ❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_image_api()
    sys.exit(0 if success else 1)
