#!/usr/bin/env python3
"""测试静音插入逻辑"""
import subprocess
import os
import tempfile

# 创建两个测试音频（各1秒）
test_dir = tempfile.mkdtemp()
audio1 = os.path.join(test_dir, 'audio1.wav')
audio2 = os.path.join(test_dir, 'audio2.wav')
silence = os.path.join(test_dir, 'silence.wav')
output = os.path.join(test_dir, 'merged.wav')

# 生成1秒测试音频
subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', audio1],
               capture_output=True, check=True)
subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1', audio2],
               capture_output=True, check=True)

# 生成0.5秒静音
subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo:d=0.5',
                '-c:a', 'pcm_s16le', '-ar', '44100', silence],
               capture_output=True, check=True)

# 创建concat文件
concat_file = os.path.join(test_dir, 'concat.txt')
with open(concat_file, 'w', encoding='utf-8') as f:
    f.write(f"file '{os.path.abspath(audio1)}'\n")
    f.write(f"file '{os.path.abspath(silence)}'\n")
    f.write(f"file '{os.path.abspath(audio2)}'\n")

# 合并
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
                '-c:a', 'pcm_s16le', '-ar', '44100', output],
               capture_output=True, check=True)

# 检查时长
result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', output],
                       capture_output=True, text=True, check=True)

duration = float(result.stdout.strip())
expected = 2.5  # 1 + 0.5 + 1

print(f"测试目录: {test_dir}")
print(f"实际时长: {duration:.2f}秒")
print(f"预期时长: {expected:.2f}秒")
print(f"差异: {abs(duration - expected):.3f}秒")

if abs(duration - expected) < 0.1:
    print("✓ 静音插入逻辑正确")
else:
    print("✗ 静音插入失败")
