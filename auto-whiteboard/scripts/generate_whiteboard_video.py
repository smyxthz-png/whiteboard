#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
白板视频生成集成器
调用 whiteboard-video-workflow 生成白板动画视频
"""

import os
import sys
import json
import subprocess
import configparser
import shutil
import hashlib


def check_ffmpeg():
    """检查ffmpeg是否安装"""
    if not shutil.which('ffmpeg'):
        print("[ERROR] ffmpeg未安装或不在PATH中", file=sys.stderr)
        print("[ERROR] 请安装ffmpeg: https://ffmpeg.org/download.html", file=sys.stderr)
        return False

    if not shutil.which('ffprobe'):
        print("[ERROR] ffprobe未安装或不在PATH中", file=sys.stderr)
        return False

    return True


def load_config(config_path):
    """加载配置文件（健壮版本）"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    config = configparser.ConfigParser()
    files_read = config.read(config_path, encoding='utf-8-sig')

    if not files_read:
        raise ValueError(f"配置文件读取失败: {config_path}")

    return config


def stable_hash(payload):
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def read_json_file(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path, payload):
    temp_path = f"{path}.tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def is_valid_asset_file(path, min_bytes=1024):
    try:
        return bool(path) and os.path.exists(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def read_env_values(env_path):
    values = {}
    if not os.path.exists(env_path):
        return values
    with open(env_path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            trimmed = line.strip()
            if not trimmed or trimmed.startswith('#') or '=' not in trimmed:
                continue
            key, value = trimmed.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def image_generation_identity(skill_dir):
    env_values = read_env_values(os.path.join(skill_dir, '.env'))
    provider = (
        os.environ.get('IMAGE_PROVIDER')
        or env_values.get('IMAGE_PROVIDER')
        or 'runninghub'
    ).strip().lower()
    normalized_provider = provider
    if provider in {'t8', 't8_image2', 't8star', 't8star_image2'}:
        normalized_provider = 't8_image2'
    elif provider in {'macode', 'macode_image2', 'image2', 'gpt-image-2'}:
        normalized_provider = 'macode_image2'
    model = (
        os.environ.get('T8_IMAGE_MODEL')
        or env_values.get('T8_IMAGE_MODEL')
        or os.environ.get('MACODE_IMAGE_MODEL')
        or env_values.get('MACODE_IMAGE_MODEL')
        or ('gpt-image-2' if normalized_provider in {'t8_image2', 'macode_image2'} else '')
    ).strip()
    size = (
        os.environ.get('T8_IMAGE_SIZE')
        or env_values.get('T8_IMAGE_SIZE')
        or os.environ.get('MACODE_IMAGE_SIZE')
        or env_values.get('MACODE_IMAGE_SIZE')
        or ''
    ).strip()
    quality = (
        os.environ.get('T8_IMAGE_QUALITY')
        or env_values.get('T8_IMAGE_QUALITY')
        or ''
    ).strip()
    return {
        'provider': normalized_provider,
        'model': model,
        'size': size,
        'quality': quality,
    }


def valid_manifest_images(manifest, expected_hash, expected_count):
    if not isinstance(manifest, dict):
        return None
    if manifest.get('prompt_hash') != expected_hash:
        return None
    image_files = manifest.get('image_files')
    if not isinstance(image_files, list) or len(image_files) != expected_count:
        return None
    if not all(is_valid_asset_file(path) for path in image_files):
        return None
    return image_files


def validate_api_key(config, section, key_name):
    """验证API Key有效性"""
    api_key = config.get(section, key_name, fallback=None)
    invalid_values = [None, '', 'your_api_key_here', 'your_runninghub_key_here', 'your_claude_api_key_here']

    if api_key in invalid_values:
        raise ValueError(f"请在config.ini [{section}]节配置有效的{key_name}")

    return api_key


def find_whiteboard_workflow_skill():
    """查找 whiteboard-video-workflow skill 目录"""
    # 从 auto-whiteboard 向上查找
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)  # auto-whiteboard
    grandparent_dir = os.path.dirname(parent_dir)  # whiteboard

    skill_path = os.path.join(grandparent_dir, 'skills', 'whiteboard-video-workflow')

    if os.path.exists(skill_path):
        return skill_path

    # 备选路径
    alt_path = os.path.join(parent_dir, '..', 'skills', 'whiteboard-video-workflow')
    if os.path.exists(alt_path):
        return os.path.abspath(alt_path)

    return None


def check_whiteboard_env(skill_dir):
    """Check whiteboard video environment"""
    print("[CHECK] Check whiteboard video environment...")

    check_script = os.path.join(skill_dir, 'scripts', 'check_env.py')

    if not os.path.exists(check_script):
        print(f"[ERROR] Environment check script not found: {check_script}", file=sys.stderr)
        return False, None

    try:
        result = subprocess.run(
            [sys.executable, check_script],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=180
        )

        print(result.stdout)

        if result.returncode != 0:
            print("[ERROR] Environment check failed", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False, None

        # 提取 PYTHON_PATH
        python_path = None
        for line in result.stdout.split('\n'):
            if line.startswith('PYTHON_PATH='):
                python_path = line.replace('PYTHON_PATH=', '').strip()
                break

        if not python_path:
            print("[WARN]  PYTHON_PATH not found, using system Python", file=sys.stderr)
            python_path = sys.executable

        print(f"[OK] Environment check passed")
        print(f"   Python: {python_path}")

        return True, python_path

    except subprocess.TimeoutExpired:
        print("[ERROR] Environment check timeout (180s)", file=sys.stderr)
        return False, None
    except Exception as e:
        print(f"[ERROR] Environment check failed: {e}", file=sys.stderr)
        return False, None


def init_dirs(skill_dir, output_dir, python_path):
    """初始化输出目录结构"""
    print("\n[MKDIR] Create output directories...")

    helper_script = os.path.join(skill_dir, 'scripts', 'workflow_helper.py')

    try:
        result = subprocess.run(
            [python_path, helper_script, 'init-dirs', output_dir],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10
        )

        if result.returncode != 0:
            print(f"[ERROR] Directory creation failed", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return None

        # 解析输出 JSON
        for line in result.stdout.split('\n'):
            if line.strip().startswith('{'):
                dirs = json.loads(line)
                print(f"[OK] Directories created")
                print(f"   Storyboard: {dirs['storyboardDir']}")
                print(f"   Images: {dirs['imageDir']}")
                print(f"   Videos: {dirs['videoDir']}")
                return dirs

        print("[ERROR] Directory info not found", file=sys.stderr)
        return None

    except subprocess.TimeoutExpired:
        print("[ERROR] Directory creation timeout (10s)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Directory creation failed: {e}", file=sys.stderr)
        return None


def generate_groups(srt_path, storyboard_dir, python_path):
    """Generate groups.json from SRT"""
    print("\n[GROUPS] Generate subtitle groups...")

    groups_script = os.path.join(os.path.dirname(__file__), 'generate_groups.py')
    groups_path = os.path.join(storyboard_dir, 'groups.json')

    try:
        result = subprocess.run(
            [python_path, groups_script, srt_path, groups_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300
        )

        print(result.stdout)

        if result.returncode != 0:
            print(f"[ERROR] Groups generation failed", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return None

        print(f"[OK] Groups generated: {groups_path}")
        return groups_path

    except subprocess.TimeoutExpired:
        print("[ERROR] Groups generation timeout (300s)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Groups generation failed: {e}", file=sys.stderr)
        return None


def generate_storyboard(skill_dir, srt_path, groups_path, storyboard_dir, python_path):
    """Generate storyboard script"""
    print("\n[STORYBOARD] Generate storyboard...")

    storyboard_script = os.path.join(skill_dir, 'scripts', 'generate-storyboard.py')
    storyboard_output = os.path.join(storyboard_dir, 'storyboard.json')

    try:
        result = subprocess.run(
            [python_path, storyboard_script, srt_path, groups_path, storyboard_output],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300
        )

        print(result.stdout)

        if result.returncode != 0:
            print(f"[ERROR] Storyboard generation failed", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return None

        if not os.path.exists(storyboard_output):
            print(f"[ERROR] Storyboard file not found: {storyboard_output}", file=sys.stderr)
            return None

        # Read scene count
        with open(storyboard_output, 'r', encoding='utf-8') as f:
            storyboard = json.load(f)
            scene_count = len(storyboard.get('scenes', []))

        print(f"[OK] Storyboard generated: {scene_count} scenes")
        return storyboard_output

    except subprocess.TimeoutExpired:
        print("[ERROR] Storyboard generation timeout (300s)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Storyboard generation failed: {e}", file=sys.stderr)
        return None


def parse_generated_image_results(stdout_text, expected_count):
    """Extract ordered image paths from generate-image.py output."""
    for line in reversed(stdout_text.splitlines()):
        if line.startswith('__RESULTS__'):
            try:
                results = json.loads(line.replace('__RESULTS__', '', 1))
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse image result JSON: {e}", file=sys.stderr)
                return None

            errors = [item for item in results if isinstance(item, dict) and item.get('error')]
            if errors:
                print("[ERROR] Image generation returned failures:", file=sys.stderr)
                for item in errors:
                    print(f"  - {item.get('error')}", file=sys.stderr)
                return None

            image_files = [item for item in results if isinstance(item, str)]
            if len(image_files) != expected_count:
                print(
                    f"[ERROR] Image result count mismatch: expected {expected_count}, got {len(image_files)}",
                    file=sys.stderr
                )
                return None

            missing = [path for path in image_files if not is_valid_asset_file(path)]
            if missing:
                print("[ERROR] Generated image files are missing:", file=sys.stderr)
                for path in missing:
                    print(f"  - {path}", file=sys.stderr)
                return None

            return image_files

    return None


def parse_batch_video_results(stdout_text, expected_count):
    """Extract ordered video paths from batch_generate.py output."""
    for line in reversed(stdout_text.splitlines()):
        if line.startswith('__RESULTS__'):
            try:
                video_files = json.loads(line.replace('__RESULTS__', '', 1))
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse batch video JSON: {e}", file=sys.stderr)
                return None

            if not isinstance(video_files, list) or len(video_files) != expected_count:
                print(
                    f"[ERROR] Video result count mismatch: expected {expected_count}, got {len(video_files) if isinstance(video_files, list) else 'invalid'}",
                    file=sys.stderr
                )
                return None

            missing = [path for path in video_files if not os.path.exists(path) or os.path.getsize(path) <= 0]
            if missing:
                print("[ERROR] Video segment files are missing or empty:", file=sys.stderr)
                for path in missing:
                    print(f"  - {path}", file=sys.stderr)
                return None

            return video_files
    return None


def generate_images(skill_dir, storyboard_path, image_dir, python_path, force=False):
    """生成白板图片"""
    print("\n[IMAGE] Generating whiteboard images...")

    # 先Generated提示词
    helper_script = os.path.join(skill_dir, 'scripts', 'workflow_helper.py')

    try:
        # 使用环境变量强制UTF-8编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            [python_path, helper_script, 'gen-prompts', storyboard_path],
            capture_output=True,
            text=False,  # 使用bytes模式
            env=env,
            timeout=300
        )

        if result.returncode != 0:
            print(f"[ERROR] Prompt generation failed", file=sys.stderr)
            return None

        # 手动解码为UTF-8
        stdout_text = result.stdout.decode('utf-8')

        # 解析提示词
        prompts = None
        for line in stdout_text.split('\n'):
            if line.strip().startswith('['):
                prompts = json.loads(line)
                break

        if not prompts:
            print("[ERROR] Prompts not found", file=sys.stderr)
            return None

        print(f"[OK] Generated {len(prompts)} image prompts")

        identity = image_generation_identity(skill_dir)
        prompt_hash = stable_hash({
            'prompts': prompts,
            'aspect_ratio': '16:9',
            'identity': identity,
        })
        image_cache_dir = os.path.join(image_dir, f"cache_{prompt_hash[:16]}")
        manifest_path = os.path.join(image_cache_dir, "image_manifest.json")
        os.makedirs(image_cache_dir, exist_ok=True)

        if force:
            for name in os.listdir(image_cache_dir):
                if name.lower().endswith(('.png', '.jpg', '.jpeg', '.tmp')):
                    os.remove(os.path.join(image_cache_dir, name))
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
        else:
            cached_images = valid_manifest_images(
                read_json_file(manifest_path),
                prompt_hash,
                len(prompts),
            )
            if cached_images:
                print(f"[REUSE] Image cache hit: {len(cached_images)} images ({prompt_hash[:12]})")
                return cached_images

        # Generate images
        image_script = os.path.join(skill_dir, 'scripts', 'generate-image.py')

        # Save prompts to temp file to avoid command line length issues
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json', delete=False) as f:
            json.dump(prompts, f, ensure_ascii=False)
            prompts_file = f.name

        try:
            # Read prompts back and pass as JSON string
            with open(prompts_file, 'r', encoding='utf-8') as f:
                prompts_json = f.read()

            print(f"[IMAGE] Calling generate-image.py with {len(prompts)} prompts...")
            print(f"[IMAGE] This may take 5-10 minutes for API calls...")

            result = subprocess.run(
                [python_path, image_script, prompts_json, '16:9', image_cache_dir],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=1800  # 增加到30分钟
            )
        finally:
            # Clean up temp file
            if os.path.exists(prompts_file):
                os.unlink(prompts_file)

        print(result.stdout)

        if result.returncode != 0:
            print(f"[ERROR] Image generation failed", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return None

        image_files = parse_generated_image_results(result.stdout, len(prompts))

        if image_files is None:
            # 兼容旧脚本输出，但仍强制校验数量，避免半成功继续。
            image_files = sorted([
                os.path.join(image_cache_dir, f)
                for f in os.listdir(image_cache_dir)
                if f.endswith(('.png', '.jpg', '.jpeg'))
            ])

        if len(image_files) != len(prompts) or not all(is_valid_asset_file(path) for path in image_files):
            print(
                f"[ERROR] Image generation incomplete: expected {len(prompts)}, got {len(image_files)}",
                file=sys.stderr
            )
            return None

        write_json_atomic(manifest_path, {
            'prompt_hash': prompt_hash,
            'identity': identity,
            'prompt_count': len(prompts),
            'image_files': image_files,
        })
        print(f"[OK] Image generation complete: {len(image_files)} images")
        return image_files

    except subprocess.TimeoutExpired:
        print("[ERROR] Image generation timeout (1800s)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Image generation failed: {e}", file=sys.stderr)
        return None


def generate_whiteboard_videos(skill_dir, image_files, durations, video_dir, python_path, fps=30, jobs=2, force=False):
    """生成白板动画视频"""
    print("\n[VIDEO] Generating whiteboard animation videos...")

    # 调用 whiteboard-animation skill
    animation_skill_dir = os.path.join(os.path.dirname(skill_dir), 'whiteboard-animation')

    if not os.path.exists(animation_skill_dir):
        print(f"[ERROR] 未找到 whiteboard-animation skill: {animation_skill_dir}", file=sys.stderr)
        return None

    batch_script = os.path.join(animation_skill_dir, 'scripts', 'batch_generate.py')

    if not os.path.exists(batch_script):
        print(f"[ERROR] Batch script not found: {batch_script}", file=sys.stderr)
        return None

    try:
        cmd = [
            python_path,
            batch_script,
            '--images'
        ] + image_files + [
            '--durations'
        ] + [str(d) for d in durations] + [
            '--output-dir', video_dir,
            '--fps', str(fps),
            '--jobs', str(jobs),
        ]
        if force:
            cmd.append('--force')

        # 使用环境变量强制UTF-8编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,  # 使用bytes模式
            env=env,
            timeout=1800  # 30 分钟
        )

        # 手动解码为UTF-8
        stdout_text = result.stdout.decode('utf-8', errors='replace')
        stderr_text = result.stderr.decode('utf-8', errors='replace')

        print(stdout_text)

        if result.returncode != 0:
            print(f"[ERROR] Video generation failed", file=sys.stderr)
            print(stderr_text, file=sys.stderr)
            return None

        video_files = parse_batch_video_results(stdout_text, len(image_files))
        if video_files is None:
            video_files = [
                os.path.join(video_dir, f"scene_{i + 1:03d}_h264.mp4")
                for i in range(len(image_files))
            ]

        if len(video_files) != len(image_files):
            print(
                f"[ERROR] Video segment count mismatch: expected {len(image_files)}, got {len(video_files)}",
                file=sys.stderr
            )
            return None

        print(f"[OK] Video generation complete: {len(video_files)} segments")
        return video_files

    except subprocess.TimeoutExpired:
        print("[ERROR] Video generation timeout (1800s)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Video generation failed: {e}", file=sys.stderr)
        return None


def generate_audio(srt_path, output_dir, config_path, python_path):
    """生成TTS音频"""
    print("\n[TTS] 生成配音...")

    # 从SRT提取句子
    sentences = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        i = 0
        while i < len(lines):
            if lines[i].strip().isdigit():
                # 跳过序号和时间戳
                i += 2
                if i < len(lines):
                    text = lines[i].strip()
                    if text:
                        sentences.append({"text": text})
                i += 1
            else:
                i += 1

    print(f"[INFO] 提取句子: {len(sentences)} 句")

    # 步骤1: 清洗文案（移除Markdown符号和特殊字符）
    raw_sentences_json = os.path.join(output_dir, 'sentences_raw.json')
    cleaned_sentences_json = os.path.join(output_dir, 'sentences_cleaned.json')

    with open(raw_sentences_json, 'w', encoding='utf-8') as f:
        json.dump(sentences, f, ensure_ascii=False, indent=2)

    print("[CLEAN] 清洗文案中...")
    clean_script = os.path.join(os.path.dirname(__file__), 'clean_script_for_tts.py')

    result = subprocess.run(
        [python_path, clean_script, '--input', raw_sentences_json, '--output', cleaned_sentences_json, '--config', config_path],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=300
    )

    if result.returncode != 0:
        print(f"[WARN] 文案清洗失败，使用原文案", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sentences_json = raw_sentences_json
    else:
        print("[OK] 文案清洗完成")
        sentences_json = cleaned_sentences_json

    # 调用TTS脚本（使用清洗后的文案）
    tts_script = os.path.join(os.path.dirname(__file__), 'generate_voiceover.py')
    audio_output_dir = os.path.join(output_dir, 'audio')
    os.makedirs(audio_output_dir, exist_ok=True)

    try:
        result = subprocess.run(
            [python_path, tts_script,
             '--sentences', sentences_json,
             '--output-dir', audio_output_dir,
             '--config', config_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=1800  # 30分钟
        )

        # 安全输出stdout
        if result.stdout:
            print(result.stdout)

        if result.returncode != 0:
            print(f"[ERROR] TTS生成失败", file=sys.stderr)
            # 安全输出stderr
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return None

        # 解析输出
        for line in result.stdout.split('\n'):
            if 'RESULT_JSON=' in line:
                result_json = json.loads(line.split('RESULT_JSON=')[1])
                voiceover_path = result_json.get('voiceover_path')
                print(f"[OK] 配音生成完成: {voiceover_path}")
                return voiceover_path

        print("[ERROR] TTS result not found", file=sys.stderr)
        return None

    except Exception as e:
        print(f"[ERROR] TTS生成失败: {e}", file=sys.stderr)
        return None


def merge_videos(skill_dir, video_files, output_dir, audio_path, python_path):
    """合并视频片段并添加音频"""
    print("\n[MERGE] Merging video segments...")

    helper_script = os.path.join(skill_dir, 'scripts', 'workflow_helper.py')

    try:
        cmd = [python_path, helper_script, 'merge-videos', output_dir] + video_files

        # 使用环境变量强制UTF-8编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,  # 使用bytes模式
            env=env,
            timeout=600
        )

        # 手动解码为UTF-8
        stdout_text = result.stdout.decode('utf-8', errors='replace')
        stderr_text = result.stderr.decode('utf-8', errors='replace')

        print(stdout_text)

        if result.returncode != 0:
            print(f"[ERROR] Video merge failed", file=sys.stderr)
            print(stderr_text, file=sys.stderr)
            return None

        # 解析输出
        merged_video = None
        for line in stdout_text.split('\n'):
            if line.strip().startswith('{'):
                merge_result = json.loads(line)
                merged_video = merge_result.get('mergedVideo')
                break

        if not merged_video:
            print("[ERROR] Merge result not found", file=sys.stderr)
            return None

        # 如果有音频，添加音频轨道和字幕
        if audio_path and os.path.exists(audio_path):
            # 步骤1: 烧录字幕到视频
            print("\n[SUBTITLE] 烧录字幕...")

            # 使用TTS生成的SRT字幕文件
            srt_file = os.path.join(os.path.dirname(audio_path), 'subtitles.srt')

            if os.path.exists(srt_file):
                video_with_subtitle = merged_video.replace('.mp4', '_with_subtitle.mp4')

                # 转换Windows路径为FFmpeg兼容格式
                srt_file_escaped = srt_file.replace('\\', '/').replace(':', '\\:')

                subtitle_result = subprocess.run([
                    'ffmpeg', '-y',
                    '-i', merged_video,
                    '-vf', f"subtitles='{srt_file_escaped}':force_style='FontName=Microsoft YaHei,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=40'",
                    '-c:a', 'copy',
                    video_with_subtitle
                ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)

                if subtitle_result.returncode == 0:
                    print("[OK] 字幕烧录成功")
                    merged_video = video_with_subtitle  # 使用带字幕的视频
                else:
                    print(f"[WARN] 字幕烧录失败，继续使用无字幕视频", file=sys.stderr)
                    print(subtitle_result.stderr, file=sys.stderr)
            else:
                print(f"[WARN] 字幕文件不存在: {srt_file}", file=sys.stderr)

            # 步骤2: 添加音频轨道
            print("\n[AUDIO] 添加音频轨道...")
            final_video = merged_video.replace('.mp4', '_final.mp4').replace('_with_subtitle_final.mp4', '_final.mp4')

            audio_merge_result = subprocess.run([
                'ffmpeg', '-y',
                '-i', merged_video,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',
                final_video
            ], capture_output=True, text=True, timeout=600)

            if audio_merge_result.returncode != 0:
                print(f"[WARN] 音频合并失败，使用无音频版本", file=sys.stderr)
                print(audio_merge_result.stderr, file=sys.stderr)
                return merged_video

            print(f"[OK] Audio added successfully: {final_video}")
            return final_video
        else:
            print(f"[OK] Video merge complete: {merged_video}")
            return merged_video

    except subprocess.TimeoutExpired:
        print("[ERROR] Video merge timeout (600s)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Video merge failed: {e}", file=sys.stderr)
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="白板视频生成集成器")
    parser.add_argument("--srt", required=True, help="SRT 字幕文件路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--config", default="../config/config.ini", help="配置文件路径")
    parser.add_argument("--audio", help="已有音频文件路径（可选，用于 standalone 合并）")
    parser.add_argument("--skip-audio", action="store_true", help="只生成无声白板视频，不重新生成 TTS")
    parser.add_argument("--fps", type=int, help="白板动画帧率，默认读取 config [Video] fps")
    parser.add_argument("--jobs", type=int, help="白板动画并发任务数，默认读取 config [Advanced] whiteboard_jobs")
    parser.add_argument("--force-images", action="store_true", help="重新生成白板图片")
    parser.add_argument("--force-video-segments", action="store_true", help="重新生成白板动画分段")

    args = parser.parse_args()

    print("=" * 60)
    print("[WHITEBOARD] Whiteboard Video Generation")
    print("=" * 60)

    # P0-1: 检查ffmpeg依赖
    print("\n[CHECK] 检查依赖...")
    if not check_ffmpeg():
        print("[ERROR] 缺少必要依赖，退出", file=sys.stderr)
        sys.exit(1)
    print("[OK] ffmpeg/ffprobe 已安装")

    # P0-2: 加载并验证配置
    if os.path.isabs(args.config):
        config_path = args.config
    else:
        project_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(project_root, args.config)

    try:
        config = load_config(config_path)
        print(f"[OK] 配置文件加载成功: {config_path}")
    except Exception as e:
        print(f"[ERROR] 配置加载失败: {e}", file=sys.stderr)
        sys.exit(1)

    # P0-3: 验证API Keys
    try:
        validate_api_key(config, 'RunningHub', 'api_key')
        if not args.skip_audio and not args.audio:
            validate_api_key(config, 'RunningHubTTS', 'api_key')
        try:
            validate_api_key(config, 'Claude', 'api_key')
        except ValueError as e:
            print(f"[WARN] {e}，将使用非 Claude 降级流程")
        print("[OK] API Keys 验证通过")
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # 查找 skill 目录
    skill_dir = find_whiteboard_workflow_skill()

    if not skill_dir:
        print("[ERROR] whiteboard-video-workflow skill not found", file=sys.stderr)
        print("   Please check project structure", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Skill 目录: {skill_dir}")

    # 检查环境
    success, python_path = check_whiteboard_env(skill_dir)
    if not success:
        sys.exit(1)

    # 初始化目录
    dirs = init_dirs(skill_dir, args.output_dir, python_path)
    if not dirs:
        sys.exit(1)

    # Generate groups
    groups_path = generate_groups(
        args.srt, dirs['storyboardDir'], python_path
    )
    if not groups_path:
        sys.exit(1)

    # Generate storyboard
    storyboard_path = generate_storyboard(
        skill_dir, args.srt, groups_path, dirs['storyboardDir'], python_path
    )
    if not storyboard_path:
        sys.exit(1)

    # 读取Storyboard获取时长
    with open(storyboard_path, 'r', encoding='utf-8') as f:
        storyboard = json.load(f)
        durations = [scene['duration'] for scene in storyboard['scenes']]

    fps = args.fps or config.getint('Video', 'fps', fallback=30)
    jobs = args.jobs or config.getint('Advanced', 'whiteboard_jobs', fallback=2)
    fps = max(12, min(fps, 60))
    jobs = max(1, min(jobs, len(durations)))
    print(f"[CONFIG] Whiteboard render: fps={fps}, jobs={jobs}, force={args.force_video_segments}")

    # 生成图片
    image_files = generate_images(
        skill_dir,
        storyboard_path,
        dirs['imageDir'],
        python_path,
        force=args.force_images,
    )
    if not image_files:
        sys.exit(1)

    # 生成视频
    video_files = generate_whiteboard_videos(
        skill_dir,
        image_files,
        durations,
        dirs['videoDir'],
        python_path,
        fps=fps,
        jobs=jobs,
        force=args.force_video_segments,
    )
    if not video_files:
        sys.exit(1)

    audio_path = None
    if args.skip_audio:
        print("\n[TTS] 跳过配音生成，使用主流程已生成的音频")
    elif args.audio:
        audio_path = os.path.abspath(args.audio)
        if not os.path.exists(audio_path):
            print(f"[ERROR] 音频文件不存在: {audio_path}", file=sys.stderr)
            sys.exit(1)
        print(f"\n[TTS] 使用已有音频: {audio_path}")
    else:
        # 生成TTS音频（standalone 模式）
        audio_path = generate_audio(
            args.srt, args.output_dir, config_path, python_path
        )
        if not audio_path:
            print("\n" + "=" * 60, file=sys.stderr)
            print("[ERROR] TTS音频生成失败，流程终止", file=sys.stderr)
            print("[ERROR] 常见原因:", file=sys.stderr)
            print("  1. config.ini [RunningHubTTS] 中API Key无效", file=sys.stderr)
            print("  2. 网络连接问题", file=sys.stderr)
            print("  3. API限流或配额不足", file=sys.stderr)
            print("  4. RunningHub TTS服务不可用", file=sys.stderr)
            print("  5. 音色文件未上传（运行: python scripts/upload_voices.py --batch）", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            sys.exit(1)

    # 合并Videos
    merged_video = merge_videos(
        skill_dir, video_files, args.output_dir, audio_path, python_path
    )
    if not merged_video:
        sys.exit(1)

    print("\n" + "=" * 60)
    print("[OK] Whiteboard video generation complete!")
    print("=" * 60)
    print(f"[OUTPUT] Output video: {merged_video}")

    # 输出 JSON 结果
    result = {
        "whiteboard_video_path": os.path.abspath(merged_video),
        "scene_count": len(durations),
        "image_count": len(image_files),
        "video_segments": len(video_files),
        "fps": fps,
        "whiteboard_jobs": jobs
    }
    print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
