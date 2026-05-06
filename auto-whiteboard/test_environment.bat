@echo off
chcp 65001 >nul
echo ========================================
echo Python 3.12 环境验证和测试
echo ========================================
echo.

echo [1/5] 检查 Python 版本...
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python 未安装或不在 PATH 中
    pause
    exit /b 1
)
echo.

echo [2/5] 检查 ffmpeg...
ffmpeg -version | findstr "ffmpeg version"
if %errorlevel% neq 0 (
    echo [ERROR] ffmpeg 未安装
    pause
    exit /b 1
)
echo.

echo [3/5] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] 依赖安装失败
    pause
    exit /b 1
)
echo.

echo [4/5] 测试文案分句（使用 Claude API）...
python scripts/text_to_srt.py --input test_sleep_script.txt --config config/config.ini
if %errorlevel% neq 0 (
    echo [ERROR] 文案分句失败
    pause
    exit /b 1
)
echo.

echo [5/5] 检查生成的句子文件...
if exist test_sleep_script_sentences.json (
    echo [SUCCESS] 句子文件已生成
    type test_sleep_script_sentences.json
) else (
    echo [ERROR] 句子文件未生成
    pause
    exit /b 1
)
echo.

echo ========================================
echo 环境验证完成！
echo ========================================
echo.
echo 下一步：运行完整测试
echo python scripts/auto_generate.py --input test_sleep_script.txt
echo.
pause
