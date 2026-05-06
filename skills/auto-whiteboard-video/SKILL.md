# Auto Whiteboard Video Generator

一键生成白板动画视频的完整工作流 skill。

## 功能

从文案到成品视频的全自动化流程：
1. 智能分句
2. TTS 配音生成
3. 白板动画生成
4. 音频混音
5. 视频合成
6. 字幕烧录

## 使用方法

```bash
/auto-whiteboard-video <文案文件路径>
```

或者直接提供文案内容：

```bash
/auto-whiteboard-video --text "你的文案内容..."
```

## 参数

- `--output-dir`: 输出目录（默认：./output）
- `--bgm`: 背景音乐文件路径（可选）
- `--keep-temp`: 保留临时文件

## 输出

- `*_final.mp4`: 完整视频（配音+动画）
- `*_with_subtitle.mp4`: 带字幕版本
- `voiceover.wav`: 配音文件
- `subtitles.srt`: 字幕文件

## 依赖

- Python 3.12+
- ffmpeg
- RunningHub API (TTS + 图片生成)
- 白板动画生成环境

## 配置

在 `auto-whiteboard/config/config.ini` 中配置 API Keys：

```ini
[RunningHubTTS]
api_key = your_tts_api_key

[RunningHub]
api_key = your_image_api_key
```
