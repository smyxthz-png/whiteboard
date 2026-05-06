# Auto Whiteboard Video Generator - Examples

## 基础使用

### 从文件生成
```bash
/auto-whiteboard-video my_script.txt
```

### 直接提供文案
```bash
/auto-whiteboard-video --text "你上一次出汗是什么时候？不是因为天热，不是因为赶路，而是真正意义上的运动出汗。"
```

## 高级选项

### 指定输出目录
```bash
/auto-whiteboard-video my_script.txt --output-dir ./my_videos
```

### 添加背景音乐
```bash
/auto-whiteboard-video my_script.txt --bgm background_music.mp3
```

### 保留临时文件（用于调试）
```bash
/auto-whiteboard-video my_script.txt --keep-temp
```

## 完整示例

```bash
/auto-whiteboard-video \
  exercise_script.txt \
  --output-dir ./output/exercise \
  --bgm music/upbeat.mp3 \
  --keep-temp
```

## 输出结构

```
output/
└── project_20260419_194327/
    ├── whiteboard_*_final.mp4          # 完整视频
    ├── whiteboard_*_with_subtitle.mp4  # 带字幕版
    ├── voiceover.wav                    # 配音
    ├── subtitles.srt                    # 字幕
    ├── sentences.json                   # 分句结果
    ├── storyboard/                      # 故事板
    ├── image/                           # 生成的图片
    ├── video/                           # 视频片段
    └── audio/                           # 音频文件
```

## 预计时间

- 短文案（< 10 句）：3-5 分钟
- 中等文案（10-20 句）：5-8 分钟
- 长文案（20-30 句）：8-12 分钟

主要耗时在 TTS 生成和图片生成（API 调用）。

## 故障排除

### 配置文件找不到
确保 `auto-whiteboard/config/config.ini` 存在并包含正确的 API Keys。

### Python 版本错误
必须使用 Python 3.12，不要使用 3.14（pydub 兼容性问题）。

### ffmpeg 未安装
Windows: 下载 ffmpeg 并添加到 PATH
Linux/Mac: `apt install ffmpeg` 或 `brew install ffmpeg`

### TTS 生成失败
检查 RunningHub TTS API Key 是否有效。

### 白板视频生成超时
检查 `skills/whiteboard-animation/.venv` 虚拟环境是否正确配置。
