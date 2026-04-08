# Teragucci

Open-source remote desktop application with full Wacom pen pressure sensitivity, H.264/H.265 video with YUV 4:4:4 chroma, and professional-grade features. Designed as a replacement for HP Anywhere (Teradici/PCoIP), Parsec, and HP RGS.

## Features

### Video Streaming
- **H.264 encoding** with YUV 4:4:4 (High 4:4:4 Predictive profile) for razor-sharp text and full color fidelity
- **H.265/HEVC** support for better compression at same quality
- **Lossless mode** for pixel-perfect accuracy
- **JPEG fallback** for environments without FFmpeg
- **Dirty-rectangle detection** in JPEG mode for bandwidth efficiency
- **Adaptive quality** with sharpness ↔ temporal stability slider

### Input
- **Full mouse control** with absolute positioning
- **Full keyboard** with Qt-to-Linux keycode mapping
- **Wacom pen/stylus** with:
  - 8192 levels of pressure sensitivity
  - Tilt X/Y
  - Rotation
  - Pen tip, eraser, and barrel button
  - Hover/proximity detection
  - Virtual uinput tablet device recognized by GIMP, Krita, Blender, etc.

### Quality Control
- **Sharpness ↔ Temporal Stability slider** — smoothly trade off between crisp individual frames and fluid motion
- **Presets**: Low Bandwidth, Balanced, Best Quality, Lossless
- **Per-setting overrides**: codec, chroma subsampling, FPS cap, bandwidth cap

### Connection Management
- **Bookmark system** with saved host, port, username, password, and quality preferences
- **Encrypted credential storage** using machine-derived keys
- **Import/Export** bookmarks as JSON
- **Search and organize** bookmarks with color labels
- **Auto-reconnect** with exponential backoff

### Health Monitoring
- **Real-time overlay** (F9 toggle) showing:
  - Round-trip latency (RTT)
  - Actual vs target FPS
  - Bandwidth usage (Mbps)
  - Dropped frames count
  - Encode/capture/input timing
  - Codec and chroma info
- **Status bar indicator** with color-coded quality dot
- **Ping/pong** latency measurement

### Security
- **TLS support** (wss://) for encrypted connections
- **Challenge-response authentication** — passwords never sent in cleartext
- **User management** via `--add-user` CLI command

### Audio
- **System audio capture** via PulseAudio/PipeWire monitor source
- **Opus encoding** for efficient low-latency audio
- **Configurable bitrate** (32-320 kbps)

### Other
- **Clipboard sync** (bidirectional text) via xclip/xsel
- **Multi-monitor support** — select individual monitors or full virtual desktop
- **Systemd service** for always-on server deployment
- **PyInstaller packaging** for standalone client builds

## Architecture

```
┌──────────────────────┐       WebSocket (ws/wss)       ┌──────────────────────┐
│   Client (Mac/Win)   │  ── JSON (input/control) ──►   │   Server (Linux)     │
│                      │  ◄── Binary (video/audio) ──   │                      │
│  PySide6 GUI         │  ◄── JSON (health/clipboard)   │  Screen Capture      │
│  ├─ RemoteViewer     │                                 │  ├─ mss (X11/XShm)  │
│  ├─ QTabletEvent     │                                 │  └─ Multi-monitor    │
│  ├─ BookmarkPanel    │                                 │                      │
│  ├─ QualitySlider    │                                 │  Video Encoder       │
│  ├─ HealthOverlay    │                                 │  ├─ FFmpeg H.264     │
│  └─ Auto-reconnect   │                                 │  ├─ FFmpeg H.265     │
│                      │                                 │  ├─ YUV 4:4:4       │
│  Bookmarks           │                                 │  └─ JPEG fallback    │
│  ├─ Encrypted creds  │                                 │                      │
│  ├─ Import/Export    │                                 │  Input Injection     │
│  └─ Color labels     │                                 │  ├─ uinput Mouse    │
│                      │                                 │  ├─ uinput Keyboard │
│                      │                                 │  └─ uinput Pen Tab  │
│                      │                                 │                      │
│                      │                                 │  Audio (PulseAudio)  │
│                      │                                 │  Clipboard (xclip)   │
│                      │                                 │  Auth + TLS          │
└──────────────────────┘                                 └──────────────────────┘
```

## Quick Start

### Server (Linux)

```bash
# Install Python dependencies
pip install -r requirements-server.txt

# Install system dependencies (Ubuntu/Debian)
sudo apt install ffmpeg pulseaudio-utils xclip

# One-time setup: configure uinput permissions
sudo bash server/setup_uinput.sh
# Log out and back in for group changes

# Optional: add a user for authentication
python -m server.main --add-user myuser

# Start the server
python -m server.main

# Full options:
python -m server.main \
  --port 9876 \
  --fps 60 \
  --codec h264 \
  --chroma yuv444 \
  --max-bandwidth 100 \
  --tls-cert cert.pem --tls-key key.pem \
  --verbose
```

### Client (Mac / Windows)

```bash
# Install dependencies
pip install -r requirements-client.txt

# Run
python -m client.main

# Or connect directly:
python -m client.main --host 192.168.1.100 --port 9876 -u myuser -p mypassword
```

### Build Standalone Client

```bash
pip install pyinstaller
python build_client.py
# Output: dist/Teragucci/
```

### Systemd Service

```bash
sudo cp server/teragucci-server.service /etc/systemd/system/
# Edit to set your username and install path
sudo systemctl daemon-reload
sudo systemctl enable --now teragucci-server
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F5 | Refresh (request full frame) |
| F9 | Toggle health overlay |
| F11 | Toggle fullscreen |
| Ctrl+N | New connection dialog |
| Ctrl+D | Disconnect |

## Configuration

### Server Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | 0.0.0.0 | Listen address |
| `--port` | 9876 | Listen port |
| `--fps` | 30 | Target frame rate |
| `--codec` | h264 | Video codec (h264/h265/jpeg) |
| `--chroma` | yuv444 | Chroma subsampling |
| `--lossless` | off | Lossless encoding |
| `--max-bandwidth` | 50 | Bandwidth cap (Mbps) |
| `--monitor` | 1 | Monitor index (0=all) |
| `--tls-cert/key` | none | TLS certificate and key |
| `--no-auth` | false | Disable authentication |
| `--no-audio` | false | Disable audio streaming |
| `--no-clipboard` | false | Disable clipboard sync |

### Quality Slider

The quality slider smoothly adjusts these encoder parameters:

| Slider Position | CRF | Preset | Behavior |
|----------------|-----|--------|----------|
| 0% (Smooth) | 28 | ultrafast | Max FPS, lower quality per frame |
| 25% | 25 | ultrafast | Prefer motion over detail |
| 50% (Balanced) | 22 | veryfast | Good trade-off |
| 75% | 18 | fast | Prefer detail, may reduce FPS |
| 100% (Sharp) | 15 | medium | Best quality per frame |

## Requirements

### Server
- Linux with X11 display
- Python 3.10+
- FFmpeg with libx264 (for H.264) and/or libx265 (for H.265)
- PulseAudio or PipeWire (for audio)
- xclip or xsel (for clipboard)
- Access to `/dev/uinput`

### Client
- macOS or Windows
- Python 3.10+ (or standalone build)
- Wacom tablet for pen pressure features (mouse works without one)

## Comparison

| Feature | Teragucci | Teradici | Parsec | HP RGS |
|---------|-----------|----------|--------|--------|
| Open Source | Yes | No | No | No |
| H.264 4:4:4 | Yes | Yes | Yes | No |
| H.265 | Yes | Yes | Yes | No |
| Pen Pressure | Yes (8192) | Limited | No | No |
| Pen Tilt | Yes | No | No | No |
| Lossless Mode | Yes | Yes | No | Yes |
| Quality Slider | Yes | Yes | Yes | No |
| Auth | Yes | Yes | Yes | Yes |
| TLS | Yes | Yes | Yes | No |
| Audio | Yes | Yes | Yes | Yes |
| Clipboard | Yes | Yes | Yes | Yes |
| Multi-Monitor | Yes | Yes | Yes | Yes |
| Bookmarks | Yes | No | Yes | No |
| Health Monitor | Yes | Limited | Yes | No |
| Auto-Reconnect | Yes | Yes | Yes | No |
| Linux Server | Yes | Yes | Yes | Yes |
| Mac Client | Yes | Yes | Yes | No |
| Windows Client | Yes | Yes | Yes | Yes |
| Free | Yes | No | Freemium | No |
