#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS 配音生成器（RunningHub API）
逐句生成配音，并根据实际音频时长生成精确对齐的 SRT 字幕
"""

import os
import sys
import io
import argparse
import json
import configparser
import time
import requests
import subprocess
from datetime import timedelta

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()

    # 确保路径存在
    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    # 读取配置
    files_read = config.read(config_path, encoding='utf-8')

    if not files_read:
        print(f"[ERROR] 无法读取配置文件: {config_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[DEBUG] 成功加载配置文件: {config_path}", file=sys.stderr)
    print(f"[DEBUG] 配置节: {config.sections()}", file=sys.stderr)

    return config


def get_audio_duration(audio_path):
    """获取音频文件时长（秒），使用ffprobe"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30
        )
        return float(result.stdout.strip())
    except subprocess.TimeoutExpired:
        print(f"[ERROR] 获取音频时长超时 (30s): {audio_path}", file=sys.stderr)
        return 0.0
    except Exception as e:
        print(f"[ERROR] 获取音频时长失败: {e}")
        return 0.0


def format_srt_timestamp(seconds):
    """格式化为 SRT 时间戳格式 HH:MM:SS,mmm"""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = int(td.total_seconds() % 60)
    millis = int((td.total_seconds() % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def mask_secret(value):
    """Mask API keys in logs."""
    if not value:
        return ''
    if len(value) <= 12:
        return '<redacted>'
    return f"{value[:8]}...{value[-4:]}"


def generate_tts_runninghub(text, output_path, api_key, reference_audio=None, tone="自然"):
    """
    使用 RunningHub AI 应用生成 TTS 配音

    参数：
    - text: 要合成的文本
    - output_path: 输出音频路径
    - api_key: RunningHub API Key
    - reference_audio: 参考音频文件名（可选，用于声音克隆）
    - tone: 语气（默认"自然"）
    """

    # RunningHub TTS AI 应用 ID
    app_id = "1966743528380510209"

    # 提交任务
    submit_url = f"https://www.runninghub.cn/openapi/v2/run/ai-app/{app_id}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # 构建请求参数
    node_info_list = [
        {
            "nodeId": "4",
            "fieldName": "prompt",
            "fieldValue": text,
            "description": "台词"
        },
        {
            "nodeId": "19",
            "fieldName": "text",
            "fieldValue": tone,
            "description": "语气"
        }
    ]

    # 如果提供了参考音频
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

    # 提交任务
    try:
        response = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get('status') not in ['QUEUED', 'RUNNING']:
            print(f"[ERROR] 任务提交失败: {result}", file=sys.stderr)
            return False

        task_id = result['taskId']
        print(f"      任务ID: {task_id}")

    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP错误 {e.response.status_code}: {e.response.text}", file=sys.stderr)
        if e.response.status_code == 401:
            print(f"[ERROR] API Key 认证失败，请检查 config.ini 中的 [RunningHubTTS] api_key", file=sys.stderr)
        return False
    except requests.exceptions.Timeout:
        print(f"[ERROR] 请求超时，请检查网络连接", file=sys.stderr)
        return False
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 网络请求失败: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] 提交任务失败: {e}", file=sys.stderr)
        return False

    # 轮询查询结果
    query_url = "https://www.runninghub.cn/openapi/v2/query"
    max_retries = 60  # 最多等待 5 分钟
    retry_interval = 5  # 每 5 秒查询一次

    for i in range(max_retries):
        time.sleep(retry_interval)

        try:
            query_payload = {"taskId": task_id}
            response = requests.post(query_url, headers=headers, json=query_payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            status = result.get('status')

            if status == 'SUCCESS':
                # 获取音频 URL
                results = result.get('results', [])
                if not results:
                    print(f"[ERROR] 未找到生成结果", file=sys.stderr)
                    return False

                audio_url = results[0].get('url')
                if not audio_url:
                    print(f"[ERROR] 未找到音频 URL", file=sys.stderr)
                    return False

                # 下载音频
                print(f"      下载音频...")
                audio_response = requests.get(audio_url, timeout=60)
                audio_response.raise_for_status()

                with open(output_path, 'wb') as f:
                    f.write(audio_response.content)

                return True

            elif status == 'FAILED':
                error_msg = result.get('errorMessage', '未知错误')
                print(f"[ERROR] 任务失败: {error_msg}", file=sys.stderr)
                return False

            elif status in ['QUEUED', 'RUNNING']:
                print(f"      等待中... ({i+1}/{max_retries})")
                continue

        except requests.exceptions.RequestException as e:
            print(f"[WARN]  查询失败 (网络错误): {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[WARN]  查询失败: {e}", file=sys.stderr)
            continue

    print(f"[ERROR] 任务超时", file=sys.stderr)
    return False


def generate_voiceover_and_srt(sentences, config, output_dir, pause=0.5):
    """
    逐句生成 TTS 配音，并根据实际时长生成 SRT

    返回：
    - voiceover_segments: [(audio_path, duration), ...]
    - srt_content: SRT 字幕内容
    - total_duration: 总时长（秒）
    """

    # 获取 RunningHub TTS API Key（优先使用RunningHubTTS配置，否则使用RunningHub配置）
    print(f"[DEBUG] Config sections: {config.sections()}", file=sys.stderr)
    print(f"[DEBUG] Has RunningHubTTS: {config.has_section('RunningHubTTS')}", file=sys.stderr)

    api_key = config.get('RunningHubTTS', 'api_key', fallback=None)
    print(f"[DEBUG] API Key from RunningHubTTS: {mask_secret(api_key)}", file=sys.stderr)

    if not api_key:
        api_key = config.get('RunningHub', 'api_key', fallback='')
        print(f"[DEBUG] API Key from RunningHub: {mask_secret(api_key)}", file=sys.stderr)

    if not api_key or api_key == 'your_runninghub_key_here':
        print("[ERROR] 请在 config.ini 中配置 RunningHub TTS API Key", file=sys.stderr)
        print("[ERROR] 请在 [RunningHubTTS] 部分设置有效的 api_key", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 使用 TTS API Key: {mask_secret(api_key)}", file=sys.stderr)

    # 加载语音库配置
    voice_library_path = config.get('TTS', 'voice_library', fallback='config/voice_library.json')
    voice_id = config.get('TTS', 'voice_id', fallback='default')

    # 如果是相对路径，转为绝对路径
    if not os.path.isabs(voice_library_path):
        project_root = os.path.dirname(os.path.dirname(__file__))
        voice_library_path = os.path.join(project_root, voice_library_path)

    # 尝试从语音库加载配置
    reference_audio = None
    tone = '自然'

    if os.path.exists(voice_library_path):
        try:
            with open(voice_library_path, 'r', encoding='utf-8') as f:
                voice_library = json.load(f)

            # 查找匹配的语音配置
            selected_voice = None
            for voice in voice_library.get('voices', []) + voice_library.get('custom_voices', []):
                if voice.get('id') == voice_id:
                    selected_voice = voice
                    break

            if selected_voice:
                # 优先使用已上传的fileName（RunningHub格式）
                reference_audio = selected_voice.get('uploaded_file_name') or selected_voice.get('reference_audio') or None
                tone = selected_voice.get('tone', '自然')
                print(f"[INFO] 使用语音库配置: {selected_voice.get('name')} ({selected_voice.get('description')})", file=sys.stderr)
                if reference_audio:
                    if reference_audio.startswith('openapi/') or '.' in reference_audio.split('/')[-1]:
                        print(f"[INFO] 参考音频: {reference_audio} (已上传到RunningHub)", file=sys.stderr)
                    else:
                        print(f"[WARN] 参考音频未上传到RunningHub，请运行: python scripts/upload_voices.py --batch", file=sys.stderr)
            else:
                print(f"[WARN] 未找到语音ID '{voice_id}'，使用默认配置", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] 加载语音库失败: {e}，使用默认配置", file=sys.stderr)

    # 配置文件中的直接设置会覆盖语音库配置
    config_reference_audio = config.get('TTS', 'reference_audio', fallback=None)
    config_tone = config.get('TTS', 'tone', fallback=None)

    if config_reference_audio:
        reference_audio = config_reference_audio
    if config_tone:
        tone = config_tone

    # 创建临时目录
    temp_dir = os.path.join(output_dir, 'temp_audio')
    os.makedirs(temp_dir, exist_ok=True)

    voiceover_segments = []
    srt_lines = []
    current_time = 0.0

    print(f"\n[TTS] 开始生成配音（共 {len(sentences)} 句）...")
    if reference_audio:
        print(f"   参考音频: {reference_audio}")
    print(f"   语气: {tone}")

    for idx, sentence in enumerate(sentences, start=1):
        # 处理字典格式的句子
        if isinstance(sentence, dict):
            sentence_text = sentence.get('text', '')
        else:
            sentence_text = sentence

        print(f"  [{idx}/{len(sentences)}] {sentence_text[:30]}...")

        # 生成音频文件
        audio_path = os.path.join(temp_dir, f"segment_{idx:03d}.mp3")

        success = generate_tts_runninghub(sentence_text, audio_path, api_key, reference_audio, tone)

        if not success:
            print(f"[ERROR] 第 {idx} 句生成失败，跳过", file=sys.stderr)
            continue

        # 获取实际时长
        duration = get_audio_duration(audio_path)
        voiceover_segments.append((audio_path, duration))

        # 生成 SRT 条目
        start_time = current_time
        end_time = current_time + duration

        srt_lines.append(str(idx))
        srt_lines.append(f"{format_srt_timestamp(start_time)} --> {format_srt_timestamp(end_time)}")
        srt_lines.append(sentence_text)
        srt_lines.append("")

        print(f"      [OK] 时长: {duration:.2f}s")

        # 更新时间（加上句间停顿）
        current_time = end_time + pause

    srt_content = "\n".join(srt_lines)
    total_duration = current_time - pause  # 去掉最后一个停顿

    return voiceover_segments, srt_content, total_duration


def merge_audio_segments(segments, output_path, pause=0.5):
    """
    合并音频片段为完整配音（使用 ffmpeg filter_complex，插入真实静音间隔）

    segments: [(audio_path, duration), ...]
    """
    print(f"\n[MERGE] 合并音频片段...")

    # 构建 filter_complex 命令：每个音频后添加 adelay 实现停顿
    inputs = []
    filter_parts = []

    for i, (audio_path, duration) in enumerate(segments):
        inputs.extend(['-i', audio_path])

        if i < len(segments) - 1:
            # 非最后一个片段：添加静音延迟
            delay_ms = int(pause * 1000)
            filter_parts.append(f"[{i}:a]apad=pad_dur={pause}[a{i}]")
        else:
            # 最后一个片段：不添加延迟
            filter_parts.append(f"[{i}:a]acopy[a{i}]")

    # 拼接所有音频
    concat_inputs = ''.join(f"[a{i}]" for i in range(len(segments)))
    filter_parts.append(f"{concat_inputs}concat=n={len(segments)}:v=0:a=1[out]")

    filter_complex = ';'.join(filter_parts)

    try:
        cmd = ['ffmpeg', '-y'] + inputs + [
            '-filter_complex', filter_complex,
            '-map', '[out]',
            '-c:a', 'pcm_s16le', '-ar', '44100',
            output_path
        ]

        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)

        # 计算总时长
        total_duration = sum(duration + pause for _, duration in segments) - pause

        print(f"   [OK] 合并完成: {output_path}")
        return total_duration
    except subprocess.TimeoutExpired:
        print(f"[ERROR] 音频合并超时 (600s)", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 合并失败: {e.stderr}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="TTS 配音生成器（精确时间对齐）")
    parser.add_argument("--sentences", required=True, help="句子列表 JSON 文件路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--config", default="../config/config.ini", help="配置文件路径")
    parser.add_argument("--pause", type=float, help="句间停顿（秒），覆盖配置文件")
    parser.add_argument("--keep-temp", action="store_true", help="保留临时音频文件")

    args = parser.parse_args()

    # 加载配置
    if os.path.isabs(args.config):
        config_path = args.config
    else:
        # 相对路径基于项目根目录（scripts的父目录）
        project_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(project_root, args.config)
    config = load_config(config_path)

    pause = args.pause if args.pause else config.getfloat('TextToSRT', 'pause', fallback=0.5)

    # 读取句子列表
    with open(args.sentences, 'r', encoding='utf-8') as f:
        sentences = json.load(f)

    if not sentences:
        print("[ERROR] 句子列表为空", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 读取句子: {len(sentences)} 句")

    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)

    # 生成配音和 SRT
    segments, srt_content, total_duration = generate_voiceover_and_srt(
        sentences, config, args.output_dir, pause
    )

    # 保存 SRT
    srt_path = os.path.join(args.output_dir, "subtitles.srt")
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    print(f"\n[SUCCESS] SRT 字幕生成: {srt_path}")

    # 合并音频
    voiceover_path = os.path.join(args.output_dir, "voiceover.wav")
    merge_audio_segments(segments, voiceover_path, pause)

    # 清理临时文件
    if not args.keep_temp:
        import shutil
        temp_dir = os.path.join(args.output_dir, 'temp_audio')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print("[CLEANUP] 临时文件已清理")

    print(f"\n[SUCCESS] 配音生成完成!")
    print(f"[OUTPUT] 配音文件: {voiceover_path}")
    print(f"[OUTPUT] 字幕文件: {srt_path}")
    print(f"[INFO] 总时长: {total_duration:.2f} 秒")

    # 输出 JSON 结果
    result = {
        "voiceover_path": os.path.abspath(voiceover_path),
        "srt_path": os.path.abspath(srt_path),
        "total_duration": total_duration,
        "segment_count": len(segments)
    }
    print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
