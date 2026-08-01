# Media Assets

The MIT License in this repository applies to source code and documentation. It does not automatically grant rights to third-party or user-supplied media.

## Bundled Runtime Assets

| File | Purpose | Licensing note |
| --- | --- | --- |
| `skills/whiteboard-animation/assets/drawing-hand-v2.png` | Drawing-hand overlay | User-supplied/processed project asset. Verify redistribution and commercial-use rights before publishing derived distributions. |
| `skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3` | Default low-volume BGM | Source filename is retained for traceability. Verify the original provider's license before redistribution or commercial use. |

## Replacing Assets

You can replace either file without changing the pipeline:

1. Use a transparent PNG with a long visible forearm for the drawing-hand overlay.
2. Use an MP3/WAV track you own or have licensed for the default BGM.
3. Keep the same filenames, or update `HAND_PATH` in `skills/whiteboard-animation/scripts/generate_whiteboard.py` and `default_bgm` in `auto-whiteboard/config/config.example.ini`.

Generated images, voiceovers, covers, and videos are outputs of third-party services. Their permitted use depends on the provider terms and the user's input rights.
