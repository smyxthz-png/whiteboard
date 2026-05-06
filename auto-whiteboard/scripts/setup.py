#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境安装脚本
"""

import os
import sys
import subprocess
import shutil


def check_python_version():
    """检查 Python 版本"""
    print("[EMOJI] 检查 Python 版本...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"[ERROR] Python 版本过低: {version.major}.{version.minor}")
        print("   需要 Python 3.8 或更高版本")
        return False
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_ffmpeg():
    """检查 ffmpeg"""
    print("\n[STORYBOARD] 检查 ffmpeg...")
    if shutil.which('ffmpeg') is None:
        print("[ERROR] 未找到 ffmpeg")
        print("\n请安装 ffmpeg:")
        print("  Windows: choco install ffmpeg")
        print("  macOS: brew install ffmpeg")
        print("  Linux: apt-get install ffmpeg")
        return False

    # 获取版本
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        version_line = result.stdout.split('\n')[0]
        print(f"[OK] {version_line}")
        return True
    except:
        print("[WARN]  ffmpeg 已安装但无法获取版本")
        return True


def install_requirements():
    """安装 Python 依赖"""
    print("\n[EMOJI] 安装 Python 依赖...")

    requirements_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')

    if not os.path.exists(requirements_path):
        print(f"[ERROR] 未找到 requirements.txt: {requirements_path}")
        return False

    try:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', requirements_path],
            check=True
        )
        print("[OK] 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 依赖安装失败: {e}")
        return False


def check_config():
    """检查配置文件"""
    print("\n[EMOJI][EMOJI]  检查配置文件...")

    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}")
        return False

    print(f"[OK] 配置文件: {config_path}")

    # 读取配置检查 API Key
    import configparser
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')

    warnings = []

    # 检查 RunningHub API Key
    rh_key = config.get('RunningHub', 'api_key', fallback='')
    if not rh_key or rh_key == 'your_runninghub_key_here':
        warnings.append("RunningHub API Key 未配置")

    # 检查 Claude API Key
    claude_key = config.get('Claude', 'api_key', fallback='')
    if not claude_key or claude_key == 'your_claude_api_key_here':
        warnings.append("Claude API Key 未配置（可选，用于智能分句）")

    if warnings:
        print("\n[WARN]  配置警告:")
        for warning in warnings:
            print(f"   - {warning}")
        print(f"\n请编辑配置文件: {config_path}")
    else:
        print("[OK] API Key 已配置")

    return True


def main():
    print("=" * 60)
    print("[EMOJI] 全自动白板视频生成系统 - 环境安装")
    print("=" * 60)

    all_ok = True

    # 检查 Python
    if not check_python_version():
        all_ok = False

    # 检查 ffmpeg
    if not check_ffmpeg():
        all_ok = False

    # 安装依赖
    if not install_requirements():
        all_ok = False

    # 检查配置
    if not check_config():
        all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("[OK] 环境安装完成！")
        print("\n下一步:")
        print("1. 编辑 config/config.ini 配置 API Keys")
        print("2. 准备文案文件（.txt）")
        print("3. 运行: python scripts/auto_generate.py --input 文案.txt")
    else:
        print("[ERROR] 环境安装未完成，请解决上述问题")
    print("=" * 60)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
