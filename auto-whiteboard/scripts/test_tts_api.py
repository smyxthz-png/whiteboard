#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify RunningHub TTS API key is valid
"""

import os
import sys
import io
import configparser
import requests
import time

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def load_config():
    """Load config.ini"""
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.ini')
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8-sig')
    return config

def test_tts_api():
    """Test TTS API with a simple request"""
    print("=" * 60)
    print("RunningHub TTS API Key Test")
    print("=" * 60)

    # Load config
    config = load_config()

    # Get API key
    api_key = config.get('RunningHubTTS', 'api_key', fallback=None)
    if not api_key:
        api_key = config.get('RunningHub', 'api_key', fallback='')

    if not api_key or api_key == 'your_runninghub_key_here':
        print("[ERROR] No valid API key found in config.ini")
        print("[ERROR] Please set api_key in [RunningHubTTS] section")
        return False

    print(f"[INFO] Testing API Key: {api_key[:8]}...{api_key[-4:]}")

    # Get optional parameters
    reference_audio = config.get('TTS', 'reference_audio', fallback=None)
    tone = config.get('TTS', 'tone', fallback='自然')

    print(f"[INFO] Tone: {tone}")
    if reference_audio:
        print(f"[INFO] Reference Audio: {reference_audio}")

    # Test text
    test_text = "这是一个测试语音合成的句子。"
    print(f"[INFO] Test Text: {test_text}")

    # RunningHub TTS AI App ID
    app_id = "1966743528380510209"
    submit_url = f"https://www.runninghub.cn/openapi/v2/run/ai-app/{app_id}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Build request
    node_info_list = [
        {
            "nodeId": "4",
            "fieldName": "prompt",
            "fieldValue": test_text,
            "description": "台词"
        },
        {
            "nodeId": "19",
            "fieldName": "text",
            "fieldValue": tone,
            "description": "语气"
        }
    ]

    if reference_audio:
        node_info_list.append({
            "nodeId": "18",
            "fieldName": "audio",
            "fieldValue": reference_audio,
            "description": "模仿的音频"
        })

    payload = {
        "nodeInfoList": node_info_list,
        "instanceType": "default",
        "usePersonalQueue": "false"
    }

    # Submit task
    print("\n[TEST] Submitting TTS task...")
    try:
        response = requests.post(submit_url, headers=headers, json=payload, timeout=30)

        print(f"[INFO] HTTP Status: {response.status_code}")

        if response.status_code == 401:
            print("[ERROR] ❌ Authentication failed - API key is invalid")
            print("[ERROR] Please check the api_key in config.ini [RunningHubTTS] section")
            return False

        if response.status_code == 403:
            print("[ERROR] ❌ Access forbidden - API key may not have TTS permissions")
            return False

        response.raise_for_status()
        result = response.json()

        print(f"[INFO] Response: {result}")

        if result.get('status') not in ['QUEUED', 'RUNNING']:
            print(f"[ERROR] ❌ Task submission failed: {result}")
            return False

        task_id = result.get('taskId')
        print(f"[SUCCESS] ✅ Task submitted successfully!")
        print(f"[INFO] Task ID: {task_id}")

        # Poll for result (wait up to 60 seconds)
        print("\n[TEST] Polling for result...")
        query_url = "https://www.runninghub.cn/openapi/v2/query"
        max_polls = 12

        for i in range(max_polls):
            time.sleep(5)

            try:
                query_payload = {"taskId": task_id}
                response = requests.post(query_url, headers=headers, json=query_payload, timeout=30)
                response.raise_for_status()
                result = response.json()

                status = result.get('status')
                print(f"[INFO] Poll {i+1}/{max_polls}: Status = {status}")

                if status == 'SUCCESS':
                    results = result.get('results', [])
                    if results and results[0].get('url'):
                        audio_url = results[0]['url']
                        print(f"\n[SUCCESS] ✅ TTS generation completed!")
                        print(f"[INFO] Audio URL: {audio_url}")
                        print("\n" + "=" * 60)
                        print("✅ API KEY IS VALID AND WORKING!")
                        print("=" * 60)
                        return True
                    else:
                        print(f"[ERROR] ❌ No audio URL in result: {result}")
                        return False

                elif status == 'FAILED':
                    error_msg = result.get('errorMessage', 'Unknown error')
                    print(f"[ERROR] ❌ Task failed: {error_msg}")
                    return False

                elif status in ['QUEUED', 'RUNNING']:
                    continue

            except Exception as e:
                print(f"[WARN] Poll error: {e}")
                continue

        print(f"[ERROR] ❌ Task timed out after {max_polls * 5} seconds")
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
    success = test_tts_api()
    sys.exit(0 if success else 1)
