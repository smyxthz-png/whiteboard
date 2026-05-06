#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音色上传管理脚本 - 上传本地音色文件到RunningHub
"""

import sys
import os
import json
import requests
import configparser

# Windows UTF-8 输出设置
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def upload_audio_to_runninghub(audio_path, api_key):
    """
    上传音频文件到RunningHub
    返回: fileName (用于TTS API的reference_audio参数)
    """
    upload_url = "https://www.runninghub.cn/openapi/v2/media/upload/binary"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    try:
        with open(audio_path, 'rb') as f:
            files = {'file': (os.path.basename(audio_path), f)}
            response = requests.post(upload_url, headers=headers, files=files, timeout=60)

        response.raise_for_status()
        result = response.json()

        if result.get('code') == 0:
            file_name = result['data']['fileName']
            download_url = result['data']['download_url']
            size = result['data']['size']

            print(f"[OK] 上传成功", file=sys.stderr)
            print(f"    文件名: {file_name}", file=sys.stderr)
            print(f"    大小: {size} bytes", file=sys.stderr)
            print(f"    下载链接: {download_url}", file=sys.stderr)
            print(f"    有效期: 1天", file=sys.stderr)

            return file_name
        else:
            print(f"[ERROR] 上传失败: {result.get('message')}", file=sys.stderr)
            return None

    except Exception as e:
        print(f"[ERROR] 上传异常: {e}", file=sys.stderr)
        return None


def update_voice_library(voice_library_path, voice_id, uploaded_file_name):
    """
    更新语音库配置，添加上传后的fileName
    """
    with open(voice_library_path, 'r', encoding='utf-8') as f:
        voice_library = json.load(f)

    # 查找并更新对应的语音配置
    updated = False
    for voice in voice_library.get('voices', []) + voice_library.get('custom_voices', []):
        if voice.get('id') == voice_id:
            voice['uploaded_file_name'] = uploaded_file_name
            updated = True
            break

    if updated:
        with open(voice_library_path, 'w', encoding='utf-8') as f:
            json.dump(voice_library, f, ensure_ascii=False, indent=2)
        print(f"[OK] 语音库已更新: {voice_id}", file=sys.stderr)
    else:
        print(f"[WARN] 未找到语音ID: {voice_id}", file=sys.stderr)


def batch_upload_voices(voice_dir, voice_library_path, api_key):
    """
    批量上传音色库中的所有音频文件
    """
    # 读取语音库配置
    with open(voice_library_path, 'r', encoding='utf-8') as f:
        voice_library = json.load(f)

    print(f"\n[UPLOAD] 开始批量上传音色文件...\n", file=sys.stderr)

    uploaded_count = 0
    failed_count = 0

    for voice in voice_library.get('voices', []) + voice_library.get('custom_voices', []):
        voice_id = voice.get('id')
        reference_audio = voice.get('reference_audio', '')

        # 跳过没有参考音频的语音
        if not reference_audio or reference_audio == '':
            continue

        # 检查是否已上传
        if voice.get('uploaded_file_name'):
            print(f"[SKIP] {voice.get('name')} - 已上传", file=sys.stderr)
            continue

        # 检查文件是否存在
        if not os.path.exists(reference_audio):
            print(f"[ERROR] {voice.get('name')} - 文件不存在: {reference_audio}", file=sys.stderr)
            failed_count += 1
            continue

        print(f"[{uploaded_count + failed_count + 1}] 上传: {voice.get('name')}", file=sys.stderr)
        print(f"    本地路径: {reference_audio}", file=sys.stderr)

        # 上传文件
        uploaded_file_name = upload_audio_to_runninghub(reference_audio, api_key)

        if uploaded_file_name:
            # 更新语音库配置
            voice['uploaded_file_name'] = uploaded_file_name
            uploaded_count += 1
        else:
            failed_count += 1

        print()  # 空行分隔

    # 保存更新后的语音库
    with open(voice_library_path, 'w', encoding='utf-8') as f:
        json.dump(voice_library, f, ensure_ascii=False, indent=2)

    print(f"\n[SUMMARY] 上传完成", file=sys.stderr)
    print(f"    成功: {uploaded_count}", file=sys.stderr)
    print(f"    失败: {failed_count}", file=sys.stderr)

    return uploaded_count, failed_count


def main():
    import argparse

    parser = argparse.ArgumentParser(description='上传音色文件到RunningHub')
    parser.add_argument('--config', default='config/config.ini', help='配置文件路径')
    parser.add_argument('--voice-library', default='config/voice_library.json', help='语音库配置文件')
    parser.add_argument('--batch', action='store_true', help='批量上传所有音色')
    parser.add_argument('--voice-id', help='单个上传指定语音ID')

    args = parser.parse_args()

    # 加载配置
    if os.path.isabs(args.config):
        config_path = args.config
    else:
        project_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(project_root, args.config)

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')

    # 获取API Key
    api_key = config.get('RunningHubTTS', 'api_key', fallback=None)
    if not api_key:
        api_key = config.get('RunningHub', 'api_key', fallback=None)

    if not api_key:
        print("[ERROR] 未配置RunningHub API Key", file=sys.stderr)
        sys.exit(1)

    # 语音库路径
    if os.path.isabs(args.voice_library):
        voice_library_path = args.voice_library
    else:
        project_root = os.path.dirname(os.path.dirname(__file__))
        voice_library_path = os.path.join(project_root, args.voice_library)

    if not os.path.exists(voice_library_path):
        print(f"[ERROR] 语音库文件不存在: {voice_library_path}", file=sys.stderr)
        sys.exit(1)

    # 批量上传
    if args.batch:
        voice_dir = "D:/whiteboard/voice"
        uploaded, failed = batch_upload_voices(voice_dir, voice_library_path, api_key)

        result = {
            "uploaded": uploaded,
            "failed": failed,
            "voice_library": voice_library_path
        }
        print(f"RESULT_JSON={json.dumps(result)}")
        sys.exit(0 if failed == 0 else 1)

    # 单个上传
    elif args.voice_id:
        with open(voice_library_path, 'r', encoding='utf-8') as f:
            voice_library = json.load(f)

        # 查找语音配置
        voice_config = None
        for voice in voice_library.get('voices', []) + voice_library.get('custom_voices', []):
            if voice.get('id') == args.voice_id:
                voice_config = voice
                break

        if not voice_config:
            print(f"[ERROR] 未找到语音ID: {args.voice_id}", file=sys.stderr)
            sys.exit(1)

        reference_audio = voice_config.get('reference_audio', '')
        if not reference_audio:
            print(f"[ERROR] 该语音没有参考音频", file=sys.stderr)
            sys.exit(1)

        if not os.path.exists(reference_audio):
            print(f"[ERROR] 文件不存在: {reference_audio}", file=sys.stderr)
            sys.exit(1)

        print(f"[UPLOAD] {voice_config.get('name')}", file=sys.stderr)
        uploaded_file_name = upload_audio_to_runninghub(reference_audio, api_key)

        if uploaded_file_name:
            update_voice_library(voice_library_path, args.voice_id, uploaded_file_name)
            result = {
                "voice_id": args.voice_id,
                "uploaded_file_name": uploaded_file_name
            }
            print(f"RESULT_JSON={json.dumps(result)}")
            sys.exit(0)
        else:
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
