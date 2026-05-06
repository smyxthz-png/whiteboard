# 快速开始指南

## 第一步：安装环境

```bash
cd auto-whiteboard
python scripts/setup.py
```

这会自动检查并安装所有依赖。

## 第二步：配置 API Keys

编辑 `config/config.ini`：

```ini
[RunningHub]
api_key = 你的_RunningHub_API_Key

[Claude]
api_key = 你的_Claude_API_Key  # 可选，用于智能分句
```

### 获取 API Keys

- **RunningHub**: https://www.runninghub.cn/
- **Claude**: https://console.anthropic.com/

## 第三步：准备文案

创建一个文本文件，例如 `my_script.txt`：

```
欢迎来到我的频道。今天我们要讲解一个重要的概念。
这个概念将改变你对世界的看法。让我们开始吧！
```

## 第四步：生成视频

### 基础用法（无背景音乐）

```bash
python scripts/auto_generate.py --input my_script.txt
```

### 添加背景音乐

```bash
python scripts/auto_generate.py \
  --input my_script.txt \
  --bgm assets/bgm/soft_music.mp3
```

### 自定义输出目录

```bash
python scripts/auto_generate.py \
  --input my_script.txt \
  --output-dir ./my_videos
```

## 输出结果

生成完成后，你会得到：

```
output/project_20260418_120000/
├── final_video.mp4      # 最终成品视频
├── subtitles.srt        # 字幕文件
├── voiceover.wav        # 配音文件
└── mixed_audio.wav      # 混音后的音频（如果有BGM）
```

## 高级用法

### 1. 测试单个组件

#### 只生成分句

```bash
python scripts/text_to_srt.py --input my_script.txt
```

#### 只生成配音

```bash
python scripts/generate_voiceover.py \
  --sentences sentences.json \
  --output-dir ./output
```

#### 只混音

```bash
python scripts/audio_mixer.py \
  --voiceover voiceover.wav \
  --bgm music.mp3 \
  --output mixed.wav
```

#### 只合成视频

```bash
python scripts/video_composer.py \
  --video video.mp4 \
  --srt subtitles.srt \
  --audio audio.wav \
  --output final.mp4
```

### 2. 验证同步性

```bash
python scripts/verify_sync.py \
  --srt output/subtitles.srt \
  --audio output/voiceover.wav
```

### 3. 自定义配置

编辑 `config/config.ini` 调整：

- 语速和停顿
- 字幕样式（字体、颜色、位置）
- 背景音乐音量
- 视频编码参数

## 常见问题

### Q: ffmpeg 未找到

**A:** 安装 ffmpeg：
- Windows: `choco install ffmpeg`
- macOS: `brew install ffmpeg`
- Linux: `apt-get install ffmpeg`

### Q: TTS 生成失败

**A:** 检查：
1. RunningHub API Key 是否正确
2. 账户余额是否充足
3. 网络连接是否正常

### Q: 字幕不同步

**A:** 运行验证脚本：
```bash
python scripts/verify_sync.py --srt subtitles.srt --audio voiceover.wav
```

如果验证失败，请检查配音生成步骤是否有错误。

### Q: 视频质量不满意

**A:** 调整 `config/config.ini` 中的视频参数：
```ini
[Video]
crf = 18  # 降低数值提高质量（18-28）
preset = slow  # 使用更慢的预设提高质量
```

## 工作流程图

```
文案文本 (my_script.txt)
    ↓
AI 智能分句 (text_to_srt.py)
    ↓
句子列表 (sentences.json)
    ↓
TTS 配音生成 (generate_voiceover.py)
    ↓
配音 + SRT (voiceover.wav + subtitles.srt)
    ↓
白板动画生成 (待集成)
    ↓
白板视频 (whiteboard_video.mp4)
    ↓
音频混音 (audio_mixer.py) [可选]
    ↓
混音音频 (mixed_audio.wav)
    ↓
视频合成 (video_composer.py)
    ↓
最终成品 (final_video.mp4)
```

## 技术支持

遇到问题？查看：
- README.md - 完整文档
- config/config.ini - 配置说明
- scripts/*.py - 源代码注释

## 下一步

1. 尝试生成你的第一个视频
2. 调整配置优化效果
3. 准备自己的背景音乐库
4. 探索高级功能
