#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify Claude API key is valid
"""

import os
import sys
import io
import configparser
import requests

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def load_config():
    """Load config.ini"""
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.ini')
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    return config

def test_claude_api():
    """Test Claude API with a simple request"""
    print("=" * 60)
    print("Claude API Key Test")
    print("=" * 60)

    # Load config
    config = load_config()

    # Get API key and base URL
    api_key = config.get('Claude', 'api_key', fallback=None)
    base_url = config.get('Claude', 'base_url', fallback='https://api.anthropic.com')

    if not api_key or api_key == 'your_claude_key_here':
        print("[ERROR] No valid API key found in config.ini")
        print("[ERROR] Please set api_key in [Claude] section")
        return False

    print(f"[INFO] Testing API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"[INFO] Base URL: {base_url}")

    # Test with a simple message
    test_message = "Hello, please respond with 'API test successful'"
    print(f"[INFO] Test Message: {test_message}")

    url = f"{base_url}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }

    # Try multiple models in order of preference
    models_to_try = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307"
    ]

    payload = {
        "model": models_to_try[0],  # Will be updated in loop
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": test_message
            }
        ]
    }

    print("\n[TEST] Sending request to Claude API...")

    # Try each model until one works
    for model in models_to_try:
        print(f"[INFO] Trying model: {model}")
        payload["model"] = model

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            print(f"[INFO] HTTP Status: {response.status_code}")

            if response.status_code == 401:
                print("[ERROR] ❌ Authentication failed - API key is invalid")
                print("[ERROR] Please check the api_key in config.ini [Claude] section")
                return False

            if response.status_code == 403:
                print("[ERROR] ❌ Access forbidden - API key may not have permissions")
                return False

            if response.status_code == 503:
                result = response.json()
                if 'model_not_found' in str(result):
                    print(f"[WARN] Model {model} not available, trying next...")
                    continue
                else:
                    response.raise_for_status()

            response.raise_for_status()
            result = response.json()

            if 'content' in result and len(result['content']) > 0:
                response_text = result['content'][0].get('text', '')
                print(f"\n[SUCCESS] ✅ Claude API responded!")
                print(f"[INFO] Working Model: {model}")
                print(f"[INFO] Response: {response_text}")
                print("\n" + "=" * 60)
                print("✅ API KEY IS VALID AND WORKING!")
                print("=" * 60)
                return True
            else:
                print(f"[ERROR] ❌ Unexpected response format: {result}")
                return False

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                print(f"[WARN] Model {model} not available, trying next...")
                continue
            print(f"[ERROR] ❌ HTTP Error {e.response.status_code}")
            print(f"[ERROR] Response: {e.response.text}")
            return False
        except requests.exceptions.Timeout:
            print(f"[ERROR] ❌ Request timeout - check network connection")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] ❌ Network error: {e}")
            return False

    print("[ERROR] ❌ No available models found")
    return False

if __name__ == "__main__":
    success = test_claude_api()
    sys.exit(0 if success else 1)
