# Teragucci

Remote desktop application with full Wacom pen/stylus pressure sensitivity support. Designed as a replacement for HP Anywhere (Teradici/PCoIP) for controlling Linux workstations from Mac and Windows clients.

## Features

- **Remote desktop streaming** with dirty-rectangle detection for efficient bandwidth
- **Full mouse control** (move, click, scroll)
- **Full keyboard control** with Qt-to-Linux keycode mapping
- **Wacom pen/stylus support** with:
  - 8192 levels of pressure sensitivity
  - Tilt X/Y
  - Rotation
  - Pen tip, eraser, and barrel button support
  - Hover/proximity detection
- **Cross-platform client** (macOS and Windows via PySide6)
- **Linux server** with virtual input device injection via uinput

## Architecture

```
┌──────────────────┐         WebSocket          ┌──────────────────┐
│   Client (Mac/   │  ──── JSON (input) ────►   │   Server (Linux) │
│    Windows)      │  ◄── Binary (frames) ────  │                  │
│                  │                             │                  │
│  PySide6 GUI     │                             │  Screen Capture  │
│  QTabletEvent    │                             │  (mss + JPEG)    │
│  pen pressure    │                             │                  │
│  tilt/rotation   │                             │  Virtual Devices │
│                  │                             │  (uinput):       │
│                  │                             │  - Mouse         │
│                  │                             │  - Keyboard      │
│                  │                             │  - Pen Tablet    │
└──────────────────┘                             └──────────────────┘
```

## Quick Start

### Server (Linux)

```bash
# Install dependencies
pip install -r requirements-server.txt

# One-time setup: configure uinput permissions
sudo bash server/setup_uinput.sh
# Log out and back in, then:

# Start the server
python -m server.main

# Or with options:
python -m server.main --port 9876 --fps 30 --quality 60 --verbose
```

### Client (Mac / Windows)

```bash
# Install dependencies
pip install -r requirements-client.txt

# Run the client
python -m client.main

# Or connect directly:
python -m client.main --host 192.168.1.100 --port 9876
```

### Build Standalone Client

```bash
pip install pyinstaller
python build_client.py
# Output in dist/Teragucci/
```

### Systemd Service (Optional)

```bash
# Edit the service file to set your username and install path
sudo cp server/teragucci-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable teragucci-server
sudo systemctl start teragucci-server
```

## Protocol

- **Input events**: JSON over WebSocket text frames (mouse, keyboard, pen with pressure/tilt)
- **Screen frames**: Binary WebSocket frames with 9-byte header (type, x, y, w, h) + JPEG data
- **Dirty rectangles**: Only changed screen regions are transmitted after the initial full frame

## Requirements

### Server
- Linux with X11 display
- Python 3.10+
- Access to `/dev/uinput` (see setup script)

### Client
- macOS or Windows
- Python 3.10+ (or standalone build)
- Wacom tablet/pen for pressure features (mouse works without one)

## Configuration

| Server Flag | Default | Description |
|-------------|---------|-------------|
| `--host`    | 0.0.0.0 | Listen address |
| `--port`    | 9876    | Listen port |
| `--fps`     | 30      | Target frame rate |
| `--quality` | 60      | JPEG quality (1-100) |
| `--monitor` | 1       | Monitor index |

| Client Flag | Default | Description |
|-------------|---------|-------------|
| `--host`    | (none)  | Server address |
| `--port`    | 9876    | Server port |
