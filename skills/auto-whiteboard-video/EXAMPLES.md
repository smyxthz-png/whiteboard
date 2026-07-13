# Examples

Generate the built-in smoke-test video:

```bash
skills/auto-whiteboard-video/skill.sh examples/demo_30s.txt \
  --output-dir output/demo \
  --project-dir output/demo/latest \
  --keep-temp
```

Generate a user script:

```bash
skills/auto-whiteboard-video/skill.sh input/my_script.txt \
  --output-dir output/my_script \
  --tts-concurrency 16 \
  --whiteboard-jobs 4
```

Generate from inline text:

```bash
skills/auto-whiteboard-video/skill.sh \
  --text "This is a short whiteboard video test." \
  --output-dir output/inline-test
```

The workflow uses the default BGM configured in `auto-whiteboard/config/config.ini`.
