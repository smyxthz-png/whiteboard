#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频混音器
将配音和背景音乐混合，输出最终音频轨道
"""

import os
import sys
import argparse
import json
import configparser
import subprocess
import shutil


def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    if not shutil.which('ffmpeg'):
        print("[ERROR] ffmpeg 未安装或不在 PATH 中", file=sys.stderr)
        print("请安装 ffmpeg: https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)
    if not shutil.which('ffprobe'):
        print("[ERROR] ffprobe 未安装或不在 PATH 中", file=sys.stderr)
        sys.exit(1)


def get_audio_duration(audio_path):
    """使用 ffprobe 获取音频时长"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 获取音频时长失败: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"[ERROR] 解析音频时长失败: {e}", file=sys.stderr)
        sys.exit(1)


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8-sig')
    return config


def mix_audio(voiceover_path, bgm_path, output_path, config):
    """
    混音：配音 + 背景音乐

    参数：
    - voiceover_path: 配音文件路径
    - bgm_path: 背景音乐文件路径
    - output_path: 输出文件路径
    - config: 配置对象
    """
    print(f"\n[AUDIO] 加载音频文件...")

    # 获取音频时长
    voiceover_duration = get_audio_duration(voiceover_path)
    print(f"  [MIC]  配音: {voiceover_duration:.2f}s")

    bgm_duration = get_audio_duration(bgm_path)
    print(f"  [MUSIC] 背景音乐: {bgm_duration:.2f}s")

    # 获取配置参数
    bgm_volume = config.getint('Audio', 'bgm_volume', fallback=-18)
    fade_in = config.getint('Audio', 'fade_in', fallback=2000)
    fade_out = config.getint('Audio', 'fade_out', fallback=3000)
    loop_bgm = config.getboolean('Audio', 'loop_bgm', fallback=True)

    print(f"\n[CONFIG] 音频处理...")

    # 构建 ffmpeg 滤镜链
    # 1. 背景音乐处理：循环、音量、淡入淡出
    fade_in_sec = fade_in / 1000.0
    fade_out_sec = fade_out / 1000.0
    fade_out_start = voiceover_duration - fade_out_sec

    # 计算循环次数
    if loop_bgm and bgm_duration < voiceover_duration:
        repeat_times = int(voiceover_duration / bgm_duration) + 1
        print(f"  [EMOJI] 背景音乐循环 {repeat_times} 次")
    else:
        repeat_times = 1

    # 背景音乐滤镜：循环 -> 裁剪 -> 音量 -> 淡入淡出
    bgm_filter = f"aloop=loop={repeat_times-1}:size=2e9,atrim=duration={voiceover_duration}"
    bgm_filter += f",volume={bgm_volume}dB"
    bgm_filter += f",afade=t=in:st=0:d={fade_in_sec}"
    bgm_filter += f",afade=t=out:st={fade_out_start}:d={fade_out_sec}"

    print(f"  [VOLUME] 背景音乐音量: {bgm_volume} dB")
    print(f"  [EFFECT] 淡入: {fade_in}ms, 淡出: {fade_out}ms")

    # 2. 混音和标准化
    print(f"\n[MIXER]  混音中...")

    # 构建完整的 ffmpeg 命令
    cmd = [
        'ffmpeg',
        '-y',  # 覆盖输出文件
        '-i', voiceover_path,
        '-i', bgm_path,
        '-filter_complex',
        f"[1:a]{bgm_filter}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-16:TP=-1.5:LRA=11",
        '-ar', '44100',  # 采样率
        '-ac', '2',  # 双声道
        output_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  [OK] 标准化完成")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ffmpeg 混音失败:", file=sys.stderr)
        print(f"命令: {' '.join(cmd)}", file=sys.stderr)
        print(f"错误输出: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    # 获取输出文件信息
    final_duration = get_audio_duration(output_path)
    file_size = os.path.getsize(output_path) / (1024 * 1024)

    print(f"\n[SAVE] 导出音频...")
    print(f"  [OK] 输出: {output_path}")
    print(f"  [EMOJI]  时长: {final_duration:.2f}s")
    print(f"  [EMOJI] 大小: {file_size:.2f} MB")

    return final_duration


def main():
    parser = argparse.ArgumentParser(description="音频混音器")
    parser.add_argument("--voiceover", required=True, help="配音文件路径")
    parser.add_argument("--bgm", required=True, help="背景音乐文件路径")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--config", default="../config/config.ini", help="配置文件路径")
    parser.add_argument("--bgm-volume", type=int, help="背景音乐音量（dB），覆盖配置文件")
    parser.add_argument("--fade-in", type=int, help="淡入时长（毫秒），覆盖配置文件")
    parser.add_argument("--fade-out", type=int, help="淡出时长（毫秒），覆盖配置文件")
    parser.add_argument("--no-loop", action="store_true", help="不循环背景音乐")

    args = parser.parse_args()

    # 检查 ffmpeg
    check_ffmpeg()

    # 检查文件存在
    if not os.path.exists(args.voiceover):
        print(f"[ERROR] 配音文件不存在: {args.voiceover}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.bgm):
        print(f"[ERROR] 背景音乐文件不存在: {args.bgm}", file=sys.stderr)
        sys.exit(1)

    # 加载配置
    config_path = os.path.join(os.path.dirname(__file__), args.config)
    config = load_config(config_path)

    # 覆盖配置（如果提供了命令行参数）
    if args.bgm_volume is not None:
        config.set('Audio', 'bgm_volume', str(args.bgm_volume))
    if args.fade_in is not None:
        config.set('Audio', 'fade_in', str(args.fade_in))
    if args.fade_out is not None:
        config.set('Audio', 'fade_out', str(args.fade_out))
    if args.no_loop:
        config.set('Audio', 'loop_bgm', 'false')

    # 创建输出目录
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 混音
    duration = mix_audio(args.voiceover, args.bgm, args.output, config)

    print(f"\n[OK] 混音完成!")

    # 输出 JSON 结果
    result = {
        "mixed_audio_path": os.path.abspath(args.output),
        "duration": duration
    }
    print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
