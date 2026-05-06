# 完整工作流程说明

## 系统架构

```
用户输入文案 (example_script.txt)
         ↓
┌────────────────────────────────────────────────────────────┐
│  步骤 1: 文案智能分句 (text_to_srt.py)                      │
│  - 使用 Claude AI 进行语义分句                              │
│  - 输出: sentences.json                                     │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│  步骤 2: TTS 配音生成 (generate_voiceover.py)              │
│  - 逐句调用 RunningHub TTS API                             │
│  - 测量每段音频实际时长                                     │
│  - 根据实际时长生成 SRT（100% 对齐）                       │
│  - 输出: voiceover.wav + subtitles.srt                     │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│  步骤 3: 白板视频生成 (generate_whiteboard_video.py)       │
│  ├─ 3.1: 解析 SRT 生成分镜 (generate-storyboard.py)        │
│  ├─ 3.2: 生成白板图片 (generate-image.py)                  │
│  ├─ 3.3: 生成白板动画 (batch_generate.py)                  │
│  └─ 3.4: 合并视频片段 (workflow_helper.py merge-videos)    │
│  - 输出: whiteboard_video.mp4                              │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│  步骤 4: 音频混音 (audio_mixer.py) [可选]                  │
│  - 配音 + 背景音乐                                          │
│  - 音量调节、淡入淡出                                       │
│  - 输出: mixed_audio.wav                                   │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│  步骤 5: 视频合成 (video_composer.py)                      │
│  - 字幕烧录（ASS 格式，支持样式）                           │
│  - 音频合成                                                 │
│  - H.264 编码输出                                           │
│  - 输出: final_video.mp4                                   │
└────────────────────────────────────────────────────────────┘
         ↓
    最终成品视频
    (带字幕、配音、背景音乐的白板动画)
```

## 核心技术特性

### 1. 100% 精确时间对齐

**问题**：如何保证字幕和配音完全同步？

**解决方案**：TTS 优先 + 实际测量

```python
# 传统方案（不准确）
文案 → 预估时长 → 生成 SRT → TTS 配音
      ❌ 预估不准，累计误差大

# 我们的方案（100% 准确）
文案 → TTS 配音 → 测量实际时长 → 生成 SRT
      ✅ 时间轴来自实际音频，零误差
```

**实现细节**：

```python
# generate_voiceover.py 核心逻辑

current_time = 0.0

for sentence in sentences:
    # 1. TTS 生成音频
    audio_path = generate_tts(sentence)
    
    # 2. 测量实际时长（精确到毫秒）
    actual_duration = get_audio_duration(audio_path)
    
    # 3. 生成 SRT 条目
    start = current_time
    end = current_time + actual_duration
    srt += f"{start} --> {end}\n{sentence}\n"
    
    # 4. 累加时间
    current_time = end + pause
```

### 2. 白板视频时长匹配

**问题**：如何确保白板视频时长与配音一致？

**解决方案**：从 SRT 提取时长，传递给白板动画生成

```python
# generate_whiteboard_video.py

# 1. 从 SRT 生成分镜
storyboard = parse_srt_to_storyboard(srt_path)

# 2. 每个场景的时长来自 SRT
for scene in storyboard:
    scene.duration = srt_entry.end - srt_entry.start  # 毫秒

# 3. 生成白板动画时使用精确时长
generate_whiteboard_animation(image, duration=scene.duration)
```

### 3. 智能 TTS 参数优化

**问题**：如何让 TTS 配音更自然？

**解决方案**：根据句子特征动态调整参数

```python
# tts_optimizer.py

def get_tts_params(text):
    analysis = analyze_sentence(text)
    
    if analysis['type'] == 'question':
        return {'tone': '疑问', 'speed': 0.95, 'pause': 0.6}
    
    elif analysis['type'] == 'exclamation':
        return {'tone': '激动', 'speed': 1.05, 'pause': 0.4}
    
    elif analysis['length'] > 30:
        return {'tone': '自然', 'speed': 0.9, 'pause': 0.7}
    
    else:
        return {'tone': '自然', 'speed': 1.0, 'pause': 0.5}
```

## 配置说明

### config/config.ini

```ini
[TTS]
provider = runninghub
reference_audio =           # 可选：声音克隆参考音频
tone = 自然                 # 语气：自然、魅惑、激动、温柔

[TextToSRT]
speed = 4.0                 # 语速（字/秒）
pause = 0.5                 # 句间停顿（秒）
min_chars = 8               # 每句最少字数
max_chars = 30              # 每句最多字数

[Audio]
bgm_volume = -18            # 背景音乐音量（dB）
fade_in = 2000              # 淡入时长（毫秒）
fade_out = 3000             # 淡出时长（毫秒）

[Subtitle]
font = Microsoft YaHei      # 字体
font_size = 48              # 字号
primary_color = &H00FFFFFF  # 文字颜色（白色）
outline_color = &H00000000  # 描边颜色（黑色）
outline_width = 3           # 描边宽度
alignment = 2               # 对齐方式（2=底部居中）
margin_bottom = 40          # 距底部边距

[Video]
resolution = 1920x1080      # 分辨率
fps = 30                    # 帧率
codec = libx264             # 视频编码
crf = 23                    # 质量（18-28）
preset = medium             # 编码预设
audio_codec = aac           # 音频编码
audio_bitrate = 192k        # 音频比特率
```

## 使用示例

### 基础用法

```bash
# 1. 准备文案
echo "欢迎来到我的频道。今天我们要讲解一个重要的概念。" > my_script.txt

# 2. 一键生成
python scripts/auto_generate.py --input my_script.txt

# 输出：
# output/project_20260418_120000/final_video.mp4
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

### 保留临时文件（调试用）

```bash
python scripts/auto_generate.py \
  --input my_script.txt \
  --keep-temp
```

## 单独运行各组件

### 只生成分句

```bash
python scripts/text_to_srt.py --input my_script.txt
# 输出: my_script_sentences.json
```

### 只生成配音和字幕

```bash
python scripts/generate_voiceover.py \
  --sentences sentences.json \
  --output-dir ./output
# 输出: voiceover.wav + subtitles.srt
```

### 只生成白板视频

```bash
python scripts/generate_whiteboard_video.py \
  --srt subtitles.srt \
  --output-dir ./output
# 输出: whiteboard_video.mp4
```

### 只混音

```bash
python scripts/audio_mixer.py \
  --voiceover voiceover.wav \
  --bgm music.mp3 \
  --output mixed.wav
```

### 只合成视频

```bash
python scripts/video_composer.py \
  --video whiteboard_video.mp4 \
  --srt subtitles.srt \
  --audio mixed.wav \
  --output final.mp4
```

### 验证同步性

```bash
python scripts/verify_sync.py \
  --srt subtitles.srt \
  --audio voiceover.wav
```

## 故障排除

### 问题 1: ffmpeg 未找到

```bash
# Windows
choco install ffmpeg

# macOS
brew install ffmpeg

# Linux
apt-get install ffmpeg
```

### 问题 2: TTS 生成失败

检查：
1. RunningHub API Key 是否正确配置
2. 账户余额是否充足
3. 网络连接是否正常

### 问题 3: 字幕不同步

运行验证脚本：
```bash
python scripts/verify_sync.py \
  --srt output/subtitles.srt \
  --audio output/voiceover.wav
```

如果验证失败，检查 TTS 生成步骤是否有错误。

### 问题 4: 白板视频生成失败

检查：
1. whiteboard-video-workflow skill 是否存在
2. RunningHub API Key 是否配置
3. Python 虚拟环境是否正确安装

### 问题 5: 视频质量不满意

调整 `config/config.ini`：

```ini
[Video]
crf = 18        # 降低数值提高质量（18-28）
preset = slow   # 使用更慢的预设提高质量
```

## 性能优化

### 1. 并行处理

当前实现是串行的，可以优化为并行：

```python
# 优化方案：TTS 和分镜生成并行
import concurrent.futures

with concurrent.futures.ThreadPoolExecutor() as executor:
    future_tts = executor.submit(generate_voiceover, sentences)
    future_storyboard = executor.submit(generate_storyboard, sentences)
    
    voiceover = future_tts.result()
    storyboard = future_storyboard.result()
```

### 2. 缓存机制

对于相同的句子，可以缓存 TTS 结果：

```python
import hashlib

def get_tts_cache_key(text, tone):
    return hashlib.md5(f"{text}_{tone}".encode()).hexdigest()

# 检查缓存
cache_key = get_tts_cache_key(sentence, tone)
if cache_key in tts_cache:
    return tts_cache[cache_key]
```

### 3. 批量 API 调用

如果 RunningHub 支持批量 TTS，可以一次提交多句：

```python
# 批量提交
results = runninghub_batch_tts(sentences)

# 逐个处理结果
for result in results:
    duration = get_audio_duration(result.audio_path)
    # ...
```

## API 成本估算

假设：
- 文案 500 字
- 分句后约 20 句
- 每句平均 25 字

**TTS 成本**：
- RunningHub TTS: 约 ¥0.1-0.3 / 20 句

**图片生成成本**：
- RunningHub 图片生成: 约 ¥0.5-1.0 / 20 张

**总成本**：约 ¥0.6-1.3 / 视频

## 扩展功能

### 1. 多语言支持

修改 `generate_voiceover.py`，支持不同语言的 TTS：

```python
def get_language_voice(language):
    voices = {
        'zh-CN': 'zh-CN-XiaoxiaoNeural',
        'en-US': 'en-US-JennyNeural',
        'ja-JP': 'ja-JP-NanamiNeural'
    }
    return voices.get(language, 'zh-CN-XiaoxiaoNeural')
```

### 2. 视频模板

支持不同的视频风格模板：

```python
templates = {
    'whiteboard': generate_whiteboard_video,
    'cartoon': generate_cartoon_video,
    'realistic': generate_realistic_video
}
```

### 3. 批量处理

支持批量处理多个文案：

```bash
python scripts/batch_generate.py \
  --input-dir ./scripts/ \
  --output-dir ./videos/
```

## 总结

这个系统实现了从文案到成品视频的全自动化流程，核心优势：

1. ✅ **100% 精确对齐** - 字幕和配音完全同步
2. ✅ **一键生成** - 无需人工干预
3. ✅ **高度可配置** - 支持自定义各种参数
4. ✅ **模块化设计** - 每个组件可独立使用
5. ✅ **完整的错误处理** - 详细的错误提示和恢复机制

适用场景：
- 教育视频制作
- 产品介绍视频
- 知识分享视频
- 营销推广视频
