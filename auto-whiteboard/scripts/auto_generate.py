#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全自动白板视频生成主控脚本
从文案到成品视频的一站式自动化工作流
"""

import os
import sys
import io
import argparse
import json
import subprocess
import configparser
from datetime import datetime

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    return config


def run_script(script_path, args_list):
    """
    运行 Python 脚本并捕获输出

    返回：(success, result_json)
    """
    cmd = [sys.executable, script_path] + args_list

    print(f"\n[EMOJI] 执行: {os.path.basename(script_path)}")
    print(f"   参数: {' '.join(args_list)}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # 打印标准输出
        if result.stdout:
            print(result.stdout)

        # 打印错误输出
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            print(f"[ERROR] 脚本执行失败，退出码: {result.returncode}", file=sys.stderr)
            return False, None

        # 提取最后一个 RESULT_JSON。子流程内部也可能调用其他脚本并打印
        # RESULT_JSON，主控只应该消费当前脚本最终输出的结果。
        result_json_lines = []
        for line in result.stdout.split('\n'):
            if line.startswith('RESULT_JSON='):
                result_json_lines.append(line.replace('RESULT_JSON=', '').strip())

        if result_json_lines:
            return True, json.loads(result_json_lines[-1])

        return True, None

    except Exception as e:
        print(f"[ERROR] 执行脚本时出错: {e}", file=sys.stderr)
        return False, None


def main():
    parser = argparse.ArgumentParser(description="全自动白板视频生成器")
    parser.add_argument("--input", required=True, help="输入文案文件路径")
    parser.add_argument("--output-dir", help="输出目录（默认：./output）")
    parser.add_argument("--bgm", help="背景音乐文件路径（可选）")
    parser.add_argument("--config", default="../config/config.ini", help="配置文件路径")
    parser.add_argument("--keep-temp", action="store_true", help="保留临时文件")

    args = parser.parse_args()

    # 获取脚本目录
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 加载配置
    if os.path.isabs(args.config):
        config_path = args.config
    else:
        config_path = os.path.join(script_dir, args.config)

    # 转为绝对路径
    config_path = os.path.abspath(config_path)

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)

    # 确定输出目录
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        output_dir = os.path.abspath(config.get('Paths', 'output_dir', fallback='./output'))

    # 创建带时间戳的子目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(output_dir, f"project_{timestamp}")
    os.makedirs(project_dir, exist_ok=True)

    print("=" * 60)
    print("[STORYBOARD] 全自动白板视频生成系统")
    print("=" * 60)
    print(f"[MKDIR] 项目目录: {project_dir}")
    print(f"[EMOJI] 输入文案: {args.input}")

    # ========== 步骤 1: 文案分句 ==========
    print("\n" + "=" * 60)
    print("[EMOJI] 步骤 1/6: 文案智能分句")
    print("=" * 60)

    sentences_path = os.path.join(project_dir, "sentences.json")
    success, result = run_script(
        os.path.join(script_dir, "text_to_srt.py"),
        ["--input", args.input, "--output", sentences_path, "--config", config_path]
    )

    if not success or not result:
        print("[ERROR] 文案分句失败", file=sys.stderr)
        sys.exit(1)

    sentence_count = result['sentence_count']
    print(f"[OK] 分句完成: {sentence_count} 句")

    # ========== 步骤 2: TTS 配音生成 + SRT 生成 ==========
    print("\n" + "=" * 60)
    print("[MIC]  步骤 2/6: TTS 配音生成（同步生成 SRT）")
    print("=" * 60)

    success, result = run_script(
        os.path.join(script_dir, "generate_voiceover.py"),
        ["--sentences", sentences_path, "--output-dir", project_dir, "--config", config_path]
    )

    if not success or not result:
        print("[ERROR] TTS 配音生成失败", file=sys.stderr)
        sys.exit(1)

    voiceover_path = result['voiceover_path']
    srt_path = result['srt_path']
    total_duration = result['total_duration']

    print(f"[OK] 配音生成完成: {total_duration:.2f}s")
    print(f"   配音: {voiceover_path}")
    print(f"   字幕: {srt_path}")

    # ========== 步骤 3: 白板视频生成 ==========
    print("\n" + "=" * 60)
    print("[IMAGE] 步骤 3/6: 白板动画视频生成")
    print("=" * 60)

    success, result = run_script(
        os.path.join(script_dir, "generate_whiteboard_video.py"),
        ["--srt", srt_path, "--output-dir", project_dir, "--config", config_path, "--skip-audio"]
    )

    if not success or not result:
        print("[ERROR] 白板视频生成失败", file=sys.stderr)
        print("\n[WARN]  可以手动运行白板视频生成:")
        print(f"   python {os.path.join(script_dir, 'generate_whiteboard_video.py')} \\")
        print(f"     --srt {srt_path} \\")
        print(f"     --output-dir {project_dir}")
        sys.exit(1)

    if 'whiteboard_video_path' not in result:
        print(f"[ERROR] 白板视频结果格式异常: {result}", file=sys.stderr)
        sys.exit(1)

    video_path = result['whiteboard_video_path']
    scene_count = result['scene_count']

    print(f"[OK] 白板视频生成完成: {scene_count} 个场景")
    print(f"   视频: {video_path}")

    # ========== 步骤 4: 音频混音 ==========
    if args.bgm:
        print("\n" + "=" * 60)
        print("[AUDIO] 步骤 4/6: 音频混音（配音 + 背景音乐）")
        print("=" * 60)

        mixed_audio_path = os.path.join(project_dir, "mixed_audio.wav")
        success, result = run_script(
            os.path.join(script_dir, "audio_mixer.py"),
            [
                "--voiceover", voiceover_path,
                "--bgm", args.bgm,
                "--output", mixed_audio_path,
                "--config", config_path
            ]
        )

        if not success:
            print("[ERROR] 音频混音失败", file=sys.stderr)
            sys.exit(1)

        final_audio_path = mixed_audio_path
        print(f"[OK] 混音完成: {final_audio_path}")
    else:
        print("\n[EMOJI]  跳过步骤 4: 未指定背景音乐")
        final_audio_path = voiceover_path

    # ========== 步骤 5: 视频合成 ==========
    print("\n" + "=" * 60)
    print("[STORYBOARD] 步骤 5/6: 视频合成（字幕烧录 + 音频）")
    print("=" * 60)

    final_video_path = os.path.join(project_dir, "final_video.mp4")
    success, result = run_script(
        os.path.join(script_dir, "video_composer.py"),
        [
            "--video", video_path,
            "--srt", srt_path,
            "--audio", final_audio_path,
            "--output", final_video_path,
            "--config", config_path
        ]
    )

    if not success:
        print("[ERROR] 视频合成失败", file=sys.stderr)
        sys.exit(1)

    file_size = result['size_mb']
    print(f"[OK] 视频合成完成: {file_size:.2f} MB")

    # ========== 步骤 6: 清理临时文件 ==========
    if not args.keep_temp:
        print("\n" + "=" * 60)
        print("[EMOJI][EMOJI]  步骤 6/6: 清理临时文件")
        print("=" * 60)

        temp_files = [sentences_path]
        if args.bgm:
            temp_files.append(voiceover_path)  # 保留混音后的，删除原始配音

        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"   [EMOJI][EMOJI]  {os.path.basename(temp_file)}")

        print("[OK] 临时文件已清理")

    # ========== 完成 ==========
    print("\n" + "=" * 60)
    print("[EMOJI] 全部完成！")
    print("=" * 60)
    print(f"[OUTPUT] 最终视频: {final_video_path}")
    print(f"[EMOJI] 字幕文件: {srt_path}")
    print(f"[MIC]  音频文件: {final_audio_path}")
    print(f"[MKDIR] 项目目录: {project_dir}")
    print(f"[EMOJI]  视频时长: {total_duration:.2f}s ({total_duration/60:.2f}分钟)")
    print(f"[EMOJI] 文件大小: {file_size:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
