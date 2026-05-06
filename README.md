# Whiteboard Video Generator

从文案自动生成白板手绘视频的工作流仓库。

## 能力

- 文案分句并生成 SRT
- RunningHub TTS 配音，并按真实音频时长对齐字幕
- 支持 RunningHub 或 macode `gpt-image-2` 生图
- 将图片转为白板手绘动画片段
- 合成字幕、配音和最终 MP4

## 目录

- `auto-whiteboard/`：一键生成主流程和核心脚本
- `skills/whiteboard-video-workflow/`：SRT 到分镜、图片、动画片段的工作流
- `skills/whiteboard-animation/`：图片转白板手绘动画的 OpenCV/PyAV 实现
- `voice/`：本地音色参考文件

## 本地配置

实际密钥文件不会提交到 Git。

```powershell
Copy-Item auto-whiteboard/config/config.example.ini auto-whiteboard/config/config.ini
Copy-Item skills/whiteboard-video-workflow/.env.example skills/whiteboard-video-workflow/.env
```

然后填入：

- `auto-whiteboard/config/config.ini`：RunningHub TTS、RunningHub 图片、可选 Claude
- `skills/whiteboard-video-workflow/.env`：`IMAGE_PROVIDER`、macode image-2 或 RunningHub 生图配置

## 快速运行

```powershell
python auto-whiteboard/scripts/auto_generate.py `
  --input your_script.txt `
  --output-dir ./output
```

当前主流程会先生成 TTS 和字幕，再生成无声白板动画，最后统一合成最终视频，避免重复 TTS。

## 环境

- Python 3.11/3.12 推荐
- ffmpeg / ffprobe 必须在 PATH 中
- `skills/whiteboard-animation/scripts/setup_env.py` 会创建并检查白板动画虚拟环境

## 注意

- `output/`、`.env`、`config.ini`、虚拟环境、日志和视频产物都被 `.gitignore` 排除。
- 大压缩包、本地测试输出和密钥不要提交。
