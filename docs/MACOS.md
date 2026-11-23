# Apple Silicon preview

Source distribution for native ARM64 Python 3.11. This port has not yet been
executed on a physical Mac; it is not a signed/notarized `.app` or DMG.

1. Copy/clone the repository to a writable folder on your Mac.
2. Install Homebrew from https://brew.sh.
3. In Terminal, change to the repository folder and run:

```bash
bash Setup_macOS.command
bash Start_Tracker_macOS.command
```

Setup installs Python 3.11, FFmpeg and COLMAP through Homebrew, then installs
the pinned Python dependencies into `.venv-macos`. It preserves existing
`config.macos.json`. Windows `config.json` is intentionally ignored on macOS.
No Rosetta environment is required. You may make the launchers executable with
`chmod +x Setup_macOS.command Start_Tracker_macOS.command` for Finder launching.

COLMAP is the default solver. GPU feature extraction defaults off on Mac;
this port does not implement Metal acceleration. GLOMAP is optional and must
be installed separately and configured if selected. Blender is optional for
export; install its Apple Silicon build in `/Applications/Blender.app`.

The CLI integration was developed against COLMAP 3.12.3. Homebrew may install
a newer version with different option names. Before production use, validate
tracking on a short clip and inspect tracking.log if a command fails.
The Qt/OpenGL viewport, video codecs, EXR/TIFF, mesh generation and Blender
export require a real Mac smoke test. OpenGL 3.3 core is requested by the app.

Tests:
```bash
.venv-macos/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Windows project paths need relinking when opening projects on Mac. Keep source
media and reconstruction folders together when transferring them.

## Preview performance

The preview toolbar offers Full / 1080 / 720 / 480 (maximum image edge in pixels).
macOS defaults to 720 to limit Retina scaling and GPU overlay readback cost.
Try 480 for complex scenes; choose Full for full-resolution 100% inspection.
These are session display settings only: source media, tracking, and export are
unchanged. Empty object overlays bypass GPU rendering. Image-sequence thumbnails
are resized in the decoder worker even when a TIFF/PNG plugin ignores scaled reads.
Source video is still decoded by Qt at source resolution; this is not a proxy-video
implementation. Improvements in frame rate must be measured on the target Mac.
