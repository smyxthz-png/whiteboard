# 全自动白板视频生成系统

从文案到成品视频的一站式自动化工作流。

## 功能特性

- ✅ 文案自动分句生成 SRT 字幕
- ✅ AI 配音（TTS）完全同步字幕
- ✅ 自动生成白板手绘动画
- ✅ 背景音乐混音
- ✅ 字幕烧录
- ✅ 一键生成最终视频

## 工作流程

```
用户文案
  ↓
文案 → SRT 生成
  ↓
TTS 配音生成（时间对齐）
  ↓
分镜解析
  ↓
AI 图片生成
  ↓
白板动画生成
  ↓
视频片段合并
  ↓
音频混音（配音 + 背景音乐）
  ↓
字幕烧录 + 音频合成
  ↓
最终成品视频
```

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 ffmpeg（必需）
# Windows: choco install ffmpeg
# macOS: brew install ffmpeg
# Linux: apt-get install ffmpeg
```

### 2. 配置 API Keys

编辑 `config/config.ini`：

```ini
[TTS]
provider = azure
api_key = your_azure_key
region = eastus
voice = zh-CN-XiaoxiaoNeural

[RunningHub]
api_key = your_runninghub_key
```

### 3. 运行

```bash
python scripts/auto_generate.py --input "你的文案.txt"
```

## 目录结构

```
auto-whiteboard/
├── scripts/              # 核心脚本
│   ├── auto_generate.py      # 主控脚本
│   ├── text_to_srt.py        # 文案转SRT
│   ├── generate_voiceover.py # TTS配音
│   ├── audio_mixer.py        # 音频混音
│   └── video_composer.py     # 视频合成
├── config/               # 配置文件
│   ├── config.ini            # 主配置
│   └── subtitle_style.ass    # 字幕样式
├── assets/               # 资源文件
│   └── bgm/                  # 背景音乐库
├── output/               # 输出目录
└── temp/                 # 临时文件
```

## 配置说明

### TTS 配置

支持多个 TTS 提供商：
- **Azure TTS**（推荐）：音质最好，时间控制精确
- **OpenAI TTS**：自然度高
- **阿里云 TTS**：中文优化

### 字幕样式

编辑 `config/subtitle_style.ass` 自定义字幕外观：
- 字体、字号
- 颜色、描边
- 位置、对齐

### 背景音乐

将 MP3 文件放入 `assets/bgm/` 目录，脚本会自动选择或指定：

```bash
python scripts/auto_generate.py --input "文案.txt" --bgm "assets/bgm/soft.mp3"
```

## 高级用法

### 自定义语速

```bash
python scripts/text_to_srt.py --input "文案.txt" --speed 4.5
```

### 调整背景音乐音量

```bash
python scripts/audio_mixer.py --bgm-volume -20
```

### 字幕位置

编辑 `config/subtitle_style.ass` 中的 `MarginV` 参数。

## 故障排除

### ffmpeg 未找到
确保 ffmpeg 已安装并在 PATH 中：
```bash
ffmpeg -version
```

### TTS 生成失败
检查 API key 配置和网络连接。

### 字幕不同步
运行同步验证脚本：
```bash
python scripts/verify_sync.py --srt output/subtitles.srt --video output/final.mp4
```

## 依赖项

- Python 3.8+
- ffmpeg
- azure-cognitiveservices-speech
- pydub
- anthropic
- srt

## License

MIT
