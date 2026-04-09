"""
Remote desktop viewer widget with full pen/tablet pressure support.

Uses PySide6's QTabletEvent for Wacom pen pressure, tilt, and rotation
on both macOS and Windows. Falls back to mouse events for standard mice.
"""

import logging
from typing import Optional, Callable

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QSize
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QMouseEvent, QKeyEvent,
    QTabletEvent, QWheelEvent, QResizeEvent,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class RemoteViewer(QWidget):
    """
    Widget that displays the remote desktop and captures all input events
    including pen/stylus with pressure sensitivity.
    """

    # Signals for input events (emitted to be picked up by the protocol layer)
    mouse_moved = Signal(float, float)  # x_norm, y_norm
    mouse_button_changed = Signal(int, bool, float, float)  # button, pressed, x, y
    mouse_scrolled = Signal(int, int, float, float)  # dx, dy, x, y
    key_changed = Signal(int, int, bool, int)  # qt_key, scan_code, pressed, modifiers
    pen_event = Signal(dict)  # Full pen event data
    request_full_frame = Signal()
    paste_requested = Signal()  # Ctrl+V or Cmd+V detected — push clipboard
    files_dropped = Signal(list)  # list of file paths dropped onto viewer

    def __init__(self, parent=None):
        super().__init__(parent)

        # Remote screen dimensions (updated on server hello)
        self._remote_width = 1920
        self._remote_height = 1080

        # The current remote screen image
        self._screen_image: Optional[QImage] = None
        self._pixmap: Optional[QPixmap] = None

        # Display scaling
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._offset_x = 0
        self._offset_y = 0

        # Stretch mode: False = preserve aspect ratio (correct geometry)
        self._stretch_fill = False

        # Monitor crop: list of monitor dicts with x, y, width, height
        # When set, only these regions of the full frame are shown (stitched side by side)
        self._monitor_regions: list = []  # empty = show everything
        # Computed composite dimensions (sum of selected monitors)
        self._composite_w = 0
        self._composite_h = 0

        # Track whether we're using pen or mouse to avoid duplicate events
        self._pen_active = False

        # Enable tablet tracking for hover events
        self.setTabletTracking(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Accept all input
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setAttribute(Qt.WA_TabletTracking, True)

        # Accept file drag-and-drop
        self.setAcceptDrops(True)

        logger.info("RemoteViewer initialized")

    def set_remote_size(self, width: int, height: int):
        """Set the remote screen dimensions."""
        self._remote_width = width
        self._remote_height = height
        self._screen_image = QImage(width, height, QImage.Format_RGB888)
        self._screen_image.fill(Qt.black)
        self._update_scaling()
        logger.info("Remote screen size: %dx%d", width, height)

    def set_monitor_regions(self, regions: list):
        """Set which monitor regions to display from the full frame.

        Args:
            regions: list of dicts with x, y, width, height (pixel coords in
                     the full virtual desktop). Empty list = show everything.
        """
        self._monitor_regions = regions
        if regions:
            # Composite: monitors laid out side by side
            self._composite_w = sum(r["width"] for r in regions)
            self._composite_h = max(r["height"] for r in regions)
        else:
            self._composite_w = 0
            self._composite_h = 0
        self._pixmap = None
        self._update_scaling()
        self.update()

    def update_full_frame(self, jpeg_data: bytes):
        """Update the entire screen from JPEG data."""
        img = QImage()
        img.loadFromData(jpeg_data, "JPEG")
        if img.isNull():
            logger.warning("Failed to decode full frame JPEG")
            return
        self._screen_image = img.convertToFormat(QImage.Format_RGB888)
        self._pixmap = None  # Invalidate cache
        self.update()

    def update_partial_frame(self, x: int, y: int, w: int, h: int, jpeg_data: bytes):
        """Update a rectangular region of the screen from JPEG data."""
        if self._screen_image is None:
            return

        region = QImage()
        region.loadFromData(jpeg_data, "JPEG")
        if region.isNull():
            logger.warning("Failed to decode partial frame JPEG")
            return

        painter = QPainter(self._screen_image)
        painter.drawImage(x, y, region)
        painter.end()
        self._pixmap = None  # Invalidate cache
        self.update()

    def _update_scaling(self):
        """Recalculate display scaling to fit remote screen in widget."""
        # Use composite dimensions if monitor regions are selected
        if self._monitor_regions:
            src_w = self._composite_w
            src_h = self._composite_h
        else:
            src_w = self._remote_width
            src_h = self._remote_height

        if src_w == 0 or src_h == 0:
            return

        widget_w = self.width()
        widget_h = self.height()

        # Always maintain aspect ratio
        src_aspect = src_w / src_h
        widget_aspect = widget_w / widget_h

        if widget_aspect > src_aspect:
            display_h = widget_h
            display_w = int(display_h * src_aspect)
        else:
            display_w = widget_w
            display_h = int(display_w / src_aspect)

        self._scale_x = display_w / src_w
        self._scale_y = display_h / src_h
        self._offset_x = (widget_w - display_w) // 2
        self._offset_y = (widget_h - display_h) // 2

    def _widget_to_remote(self, x: float, y: float) -> tuple:
        """Convert widget coordinates to normalized remote coordinates (0.0-1.0).

        When monitor regions are active, maps through the composite layout
        back to full virtual desktop coordinates so XTest moves the cursor
        to the correct position.
        """
        if not self._monitor_regions:
            # Simple: widget → full remote desktop
            rx = (x - self._offset_x) / (self._scale_x * self._remote_width)
            ry = (y - self._offset_y) / (self._scale_y * self._remote_height)
            return max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))

        # Composite mode: find which monitor the click is in
        # Convert widget coords to composite pixel coords
        cx = (x - self._offset_x) / self._scale_x
        cy = (y - self._offset_y) / self._scale_y

        # Walk through monitors (laid out side by side)
        composite_x = 0
        for region in self._monitor_regions:
            rw = region["width"]
            rh = region["height"]
            if cx < composite_x + rw:
                # Click is in this monitor
                local_x = cx - composite_x
                local_y = cy
                # Map back to full virtual desktop
                desktop_x = region["x"] + local_x
                desktop_y = region["y"] + local_y
                rx = desktop_x / self._remote_width
                ry = desktop_y / self._remote_height
                return max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))
            composite_x += rw

        # Past the last monitor — clamp to last monitor's right edge
        last = self._monitor_regions[-1]
        rx = (last["x"] + last["width"] - 1) / self._remote_width
        ry = cy / self._remote_height if self._remote_height else 0
        return max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))

    # --- Paint ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)

        if self._screen_image is None:
            painter.end()
            return

        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._pixmap is None:
            self._pixmap = QPixmap.fromImage(self._screen_image)

        if not self._monitor_regions:
            # No crop — draw the full image scaled
            src_w = self._remote_width
            src_h = self._remote_height
            display_w = int(self._scale_x * src_w)
            display_h = int(self._scale_y * src_h)
            painter.drawPixmap(
                self._offset_x, self._offset_y,
                display_w, display_h,
                self._pixmap,
            )
        else:
            # Crop and stitch selected monitors side by side
            dest_x = self._offset_x
            for region in self._monitor_regions:
                # Source rect in the full pixmap
                src_x = region["x"]
                src_y = region["y"]
                src_w = region["width"]
                src_h = region["height"]

                # Destination rect in the widget
                dest_w = int(self._scale_x * src_w)
                dest_h = int(self._scale_y * src_h)
                dest_y = self._offset_y

                painter.drawPixmap(
                    QRectF(dest_x, dest_y, dest_w, dest_h),
                    self._pixmap,
                    QRectF(src_x, src_y, src_w, src_h),
                )
                dest_x += dest_w

        painter.end()

    def resizeEvent(self, event: QResizeEvent):
        self._update_scaling()
        super().resizeEvent(event)

    # --- Tablet/Pen Events (priority over mouse) ---

    def tabletEvent(self, event: QTabletEvent):
        """Handle Wacom/stylus tablet events with full pressure data."""
        # Only handle real pen/eraser devices — macOS trackpads generate
        # tablet events that would block normal mouse input
        pointer_type = event.pointerType()
        if pointer_type not in (QTabletEvent.PointerType.Pen,
                                QTabletEvent.PointerType.Eraser):
            event.ignore()
            return

        self._pen_active = True
        event.accept()

        pos = event.position()
        nx, ny = self._widget_to_remote(pos.x(), pos.y())

        # Determine pen type
        if pointer_type == QTabletEvent.PointerType.Eraser:
            pen_type = "eraser"
        else:
            pen_type = "pen"

        # Determine if pen is pressed (tip touching)
        pressed = event.pressure() > 0.0
        hovering = not pressed

        # Barrel button detection
        button = 0
        if event.buttons() & Qt.LeftButton:
            button = 1  # tip
        if event.buttons() & Qt.MiddleButton:
            button = 3  # barrel

        event_type = event.type()
        if event_type == QTabletEvent.TabletPress:
            pressed = True
            hovering = False
            button = 1
        elif event_type == QTabletEvent.TabletRelease:
            pressed = False
            hovering = True
            button = 0

        pen_data = {
            "x": nx,
            "y": ny,
            "pressure": event.pressure(),
            "tilt_x": event.xTilt(),
            "tilt_y": event.yTilt(),
            "rotation": event.rotation(),
            "button": button,
            "pressed": pressed,
            "hovering": hovering,
            "pen_type": pen_type,
        }

        self.pen_event.emit(pen_data)

        # Mark pen inactive after release + leave
        if event_type == QTabletEvent.TabletRelease:
            self._pen_active = False

    # --- Mouse Events ---

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._pen_active:
            return  # Tablet is handling this
        pos = event.position()
        nx, ny = self._widget_to_remote(pos.x(), pos.y())
        self.mouse_moved.emit(nx, ny)

    def mousePressEvent(self, event: QMouseEvent):
        if self._pen_active:
            return
        pos = event.position()
        nx, ny = self._widget_to_remote(pos.x(), pos.y())
        button = self._qt_button_to_int(event.button())
        self.mouse_button_changed.emit(button, True, nx, ny)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._pen_active:
            return
        pos = event.position()
        nx, ny = self._widget_to_remote(pos.x(), pos.y())
        button = self._qt_button_to_int(event.button())
        self.mouse_button_changed.emit(button, False, nx, ny)

    def wheelEvent(self, event: QWheelEvent):
        pos = event.position()
        nx, ny = self._widget_to_remote(pos.x(), pos.y())
        delta = event.angleDelta()
        # Convert to discrete scroll steps (120 units = 1 step)
        dx = delta.x() // 120
        dy = delta.y() // 120
        self.mouse_scrolled.emit(dx, dy, nx, ny)

    # --- Keyboard Events ---

    def keyPressEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():
            return
        key = self._remap_key(event.key())
        modifiers = self._qt_modifiers_to_int(event.modifiers())
        logger.debug("Key press: key=0x%x mod=0x%x", key, modifiers)

        # Detect paste: Ctrl+V or Cmd+V → ensure clipboard is synced to server
        if key == Qt.Key_V and (modifiers & 2):  # bit 2 = Ctrl on wire
            self.paste_requested.emit()

        self.key_changed.emit(key, key, True, modifiers)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():
            return
        key = self._remap_key(event.key())
        modifiers = self._qt_modifiers_to_int(event.modifiers())
        self.key_changed.emit(key, key, False, modifiers)
        event.accept()

    @staticmethod
    def _remap_key(key: int) -> int:
        """On macOS, both Command and Control → Control_L on Linux."""
        import sys
        if sys.platform == "darwin":
            if key == Qt.Key_Meta:
                return Qt.Key_Control   # Command → Control_L
            # Physical Control already maps to Qt.Key_Control — no change needed
        return key

    # --- Helpers ---

    @staticmethod
    def _qt_button_to_int(button) -> int:
        if button == Qt.LeftButton:
            return 1
        elif button == Qt.MiddleButton:
            return 2
        elif button == Qt.RightButton:
            return 3
        return 1

    @staticmethod
    def _qt_modifiers_to_int(mods) -> int:
        result = 0
        if mods & Qt.ShiftModifier:
            result |= 1
        if mods & Qt.AltModifier:
            result |= 4
        import sys
        if sys.platform == "darwin":
            # macOS: both Command and Control → Ctrl on Linux
            # Command+V = paste, Control+C = SIGINT — both need Ctrl
            if mods & (Qt.ControlModifier | Qt.MetaModifier):
                result |= 2
        else:
            if mods & Qt.ControlModifier:
                result |= 2
            if mods & Qt.MetaModifier:
                result |= 8
        return result

    # --- Drag and Drop ---

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path:
                    paths.append(path)
            if paths:
                logger.info("Files dropped: %s", paths)
                self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def sizeHint(self) -> QSize:
        return QSize(self._remote_width, self._remote_height)

    def minimumSizeHint(self) -> QSize:
        return QSize(640, 480)
