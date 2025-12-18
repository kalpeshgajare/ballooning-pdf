import sys
import tempfile
import math
import os
import fitz  # PyMuPDF
from PyQt5 import QtWidgets, QtGui, QtCore
from PIL import Image, ImageDraw, ImageFont

# ============================================================================
#  CUSTOM COMPASS WIDGET (New Feature)
# ============================================================================
class CompassWidget(QtWidgets.QWidget):
    """
    A 3x3 Grid of arrow buttons to select rotation angle.
    Visualizes the direction of the balloon tip.
    """
    angleChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Compact layout
        layout = QtWidgets.QGridLayout(self)
        layout.setSpacing(1)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # Mapping: Position (row, col) -> (Angle, Symbol)
        # Note: 0 degrees = Pointing Right. 
        # Angles increase clockwise (Standard screen coordinates Y-down)
        # 0=Right, 90=Down, 180=Left, 270=Up
        buttons_config = [
            (0, 0, 225, "↖"), (0, 1, 270, "↑"), (0, 2, 315, "↗"),
            (1, 0, 180, "←"),                   (1, 2, 0,   "→"),
            (2, 0, 135, "↙"), (2, 1, 90,  "↓"), (2, 2, 45,  "↘")
        ]

        self.btn_group = QtWidgets.QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for r, c, angle, text in buttons_config:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(24, 24)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    font-weight: bold; 
                    font-size: 14px;
                    border: 1px solid #ccc;
                    background-color: #f0f0f0;
                }
                QPushButton:checked {
                    background-color: #3b82f6; 
                    color: white;
                    border: 1px solid #2563eb;
                }
            """)
            
            # Default selection (Right / 0 degrees)
            if angle == 0:
                btn.setChecked(True)

            # Connect signal
            btn.clicked.connect(lambda _, a=angle: self.emit_angle(a))
            
            self.btn_group.addButton(btn, angle)
            layout.addWidget(btn, r, c)

        # Center Widget (Just a visual dot or label)
        center_lbl = QtWidgets.QLabel("●")
        center_lbl.setAlignment(QtCore.Qt.AlignCenter)
        center_lbl.setStyleSheet("color: #888; font-size: 8px;")
        layout.addWidget(center_lbl, 1, 1)

    def emit_angle(self, angle):
        self.angleChanged.emit(angle)
    
    def set_angle(self, angle):
        """Programmatically set angle (if needed)"""
        btn = self.btn_group.button(angle)
        if btn:
            btn.setChecked(True)


# ============================================================================
#  MAIN APPLICATION
# ============================================================================

class Canvas(QtWidgets.QWidget):
    """
    High-Performance Canvas.
    Renders markers dynamically on top of the image without modifying pixel data.
    """
    marker_added = QtCore.pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.pixmap_item = None     
        self.markers = []           
        
        self.circle_radius = 20
        self.number_font_size = 12
        self.border_thickness = 2
        
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setAttribute(QtCore.Qt.WA_AcceptTouchEvents)

    def update_view(self, pixmap, markers, radius):
        self.pixmap_item = pixmap
        self.markers = markers
        self.circle_radius = radius
        
        self.border_thickness = max(1, int(radius / 7.5))
        self.number_font_size = int(radius * 0.9)
        
        if self.pixmap_item:
            self.setMinimumSize(self.pixmap_item.width(), self.pixmap_item.height())
        self.update() 

    def get_image_rect(self):
        if not self.pixmap_item:
            return QtCore.QRect(0,0,0,0)
            
        pw = self.pixmap_item.width()
        ph = self.pixmap_item.height()
        ww = self.width()
        wh = self.height()

        x = (ww - pw) // 2 if ww > pw else 0
        y = (wh - ph) // 2 if wh > ph else 0
        return QtCore.QRect(x, y, pw, ph)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(220, 220, 220)) 

        if not self.pixmap_item:
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Open a File (Ctrl+O) to Start")
            return

        img_rect = self.get_image_rect()
        painter.drawPixmap(img_rect.topLeft(), self.pixmap_item)

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        font = QtGui.QFont("Arial", self.number_font_size, QtGui.QFont.Bold)
        painter.setFont(font)

        for rel_x, rel_y, num, angle in self.markers:
            tip_x = img_rect.x() + (rel_x * img_rect.width())
            tip_y = img_rect.y() + (rel_y * img_rect.height())
            self._draw_single_balloon(painter, num, tip_x, tip_y, angle)

    def _draw_single_balloon(self, painter, num, tip_x, tip_y, angle_deg):
        r = self.circle_radius
        tail_len = int(r * 1.2)
        theta = math.radians(angle_deg)
        dx = math.cos(theta)
        dy = math.sin(theta)

        cx = tip_x - dx * (tail_len + r)
        cy = tip_y - dy * (tail_len + r)

        tail_width_offset = r * 0.5
        pdx, pdy = -dy, dx 
        
        p_tip = QtCore.QPointF(tip_x, tip_y)
        p_base1 = QtCore.QPointF(cx + pdx * tail_width_offset, cy + pdy * tail_width_offset)
        p_base2 = QtCore.QPointF(cx - pdx * tail_width_offset, cy - pdy * tail_width_offset)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(255, 0, 0))
        painter.drawPolygon(QtGui.QPolygonF([p_tip, p_base1, p_base2]))

        painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 0), self.border_thickness))
        painter.setBrush(QtGui.QColor(255, 255, 255))
        painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)

        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0)))
        rect = QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r)
        painter.drawText(rect, QtCore.Qt.AlignCenter, str(num))

    def mousePressEvent(self, event):
        if not self.pixmap_item: return
        if event.button() == QtCore.Qt.LeftButton:
            img_rect = self.get_image_rect()
            x = event.x() - img_rect.x()
            y = event.y() - img_rect.y()
            if 0 <= x < img_rect.width() and 0 <= y < img_rect.height():
                self.marker_added.emit(x, y)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Balloon Marker Tool - Compass Edition")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self.source_path = None
        self.source_type = None
        self.source_doc = None      
        self.base_pixmap = None     
        
        self.markers = []           
        self.undone_markers = []
        
        self.zoom_level = 1.0
        self.current_rotation = 0 # Default 0 (Right)

        # UI Components
        self.canvas = Canvas()
        self.canvas.marker_added.connect(self.add_marker)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll.viewport().setAttribute(QtCore.Qt.WA_AcceptTouchEvents)
        self.scroll.grabGesture(QtCore.Qt.PinchGesture)
        
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.setup_toolbar(layout)
        layout.addWidget(self.scroll)
        
        self.status_label = QtWidgets.QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status_label)
        self.setCentralWidget(container)
        
        # Shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+O"), self).activated.connect(self.open_file)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+S"), self).activated.connect(self.save_file)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Z"), self).activated.connect(self.undo_marker)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Y"), self).activated.connect(self.redo_marker)

    def setup_toolbar(self, parent_layout):
        toolbar = QtWidgets.QToolBar("Main Toolbar")
        toolbar.setIconSize(QtCore.QSize(24, 24))
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolButton {
                font-size: 14px; 
                font-weight: bold; 
                padding: 6px; 
                margin: 2px;
            }
        """)
        self.addToolBar(toolbar)

        def add_btn(text, func, shortcut=None):
            btn = QtWidgets.QAction(text, self)
            btn.triggered.connect(func)
            if shortcut: btn.setShortcut(shortcut)
            toolbar.addAction(btn)
            return btn

        add_btn("📂 Open", self.open_file, "Ctrl+O")
        add_btn("💾 Save", self.save_file, "Ctrl+S")
        toolbar.addSeparator()
        add_btn("↩ Undo", self.undo_marker, "Ctrl+Z")
        add_btn("↪ Redo", self.redo_marker, "Ctrl+Y")
        add_btn("🗑 Clear", self.clear_all_markers)
        toolbar.addSeparator()
        
        # --- NEW COMPASS WIDGET ---
        self.compass = CompassWidget()
        self.compass.angleChanged.connect(self.set_rotation)
        toolbar.addWidget(self.compass)
        
        toolbar.addSeparator()
        
        # Zoom Controls
        self.zoom_label = QtWidgets.QLabel("  100%  ")
        btn_zoom_out = QtWidgets.QPushButton(" - ")
        btn_zoom_out.setFixedWidth(30)
        btn_zoom_out.clicked.connect(self.zoom_out)
        
        btn_zoom_in = QtWidgets.QPushButton(" + ")
        btn_zoom_in.setFixedWidth(30)
        btn_zoom_in.clicked.connect(self.zoom_in)

        toolbar.addWidget(btn_zoom_out)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(btn_zoom_in)
        
        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel(" Size: "))
        self.spin_size = QtWidgets.QSpinBox()
        self.spin_size.setRange(10, 100)
        self.spin_size.setValue(20)
        self.spin_size.valueChanged.connect(self.update_view_request)
        toolbar.addWidget(self.spin_size)

    # =========================================================================
    #  LOGIC
    # =========================================================================
    
    def set_rotation(self, angle):
        """Called when a user clicks an arrow in the Compass."""
        self.current_rotation = angle
        self.status_label.setText(f"Rotation set to {angle}°")

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0: self.zoom_in()
            else: self.zoom_out()
        else:
            super().wheelEvent(event)

    def event(self, event):
        if event.type() == QtCore.QEvent.NativeGesture:
            if event.gestureType() == QtCore.Qt.ZoomNativeGesture:
                scale_factor = event.value()
                self.zoom_level += scale_factor * 1.5 
                if self.zoom_level < 0.1: self.zoom_level = 0.1
                if self.zoom_level > 5.0: self.zoom_level = 5.0
                self.update_view_request()
                return True
        return super().event(event)

    def open_file(self):
        file_filter = "All Supported (*.pdf *.png *.jpg *.jpeg *.bmp);;PDF (*.pdf);;Images (*.png *.jpg *.jpeg)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open File", "", file_filter)
        if not path: return

        self.source_path = path
        self.markers = []
        self.undone_markers = []
        
        if path.lower().endswith(".pdf"):
            self.source_type = 'pdf'
            self.source_doc = fitz.open(path)
            page = self.source_doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0)) 
            img = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888)
            self.base_pixmap = QtGui.QPixmap.fromImage(img)
        else:
            self.source_type = 'image'
            self.source_doc = None
            self.base_pixmap = QtGui.QPixmap(path)

        self.zoom_level = 1.0 if self.base_pixmap.width() < 1500 else 0.5 
        self.update_view_request()
        self.status_label.setText(f"Loaded: {os.path.basename(path)}")

    def update_view_request(self):
        if not self.base_pixmap: return
        w = int(self.base_pixmap.width() * self.zoom_level)
        h = int(self.base_pixmap.height() * self.zoom_level)
        if w <= 0 or h <= 0: return

        scaled = self.base_pixmap.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        visual_radius = int(self.spin_size.value() * self.zoom_level)
        self.canvas.update_view(scaled, self.markers, visual_radius)
        self.zoom_label.setText(f"  {int(self.zoom_level*100)}%  ")

    def add_marker(self, x, y):
        view_w = self.canvas.pixmap_item.width()
        view_h = self.canvas.pixmap_item.height()
        rel_x = x / view_w
        rel_y = y / view_h
        
        count = len(self.markers) + 1
        self.markers.append((rel_x, rel_y, count, self.current_rotation))
        self.undone_markers.clear()
        self.canvas.update() 
        self.status_label.setText(f"Marker {count} added")

    def undo_marker(self):
        if self.markers:
            self.undone_markers.append(self.markers.pop())
            self.canvas.update()

    def redo_marker(self):
        if self.undone_markers:
            self.markers.append(self.undone_markers.pop())
            self.canvas.update()

    def clear_all_markers(self):
        self.markers.clear()
        self.undone_markers.clear()
        self.canvas.update()

    def zoom_in(self):
        self.zoom_level += 0.1
        self.update_view_request()

    def zoom_out(self):
        if self.zoom_level > 0.1:
            self.zoom_level -= 0.1
            self.update_view_request()

    def save_file(self):
        if not self.source_path or not self.markers:
            QtWidgets.QMessageBox.warning(self, "Warning", "Nothing to save!")
            return

        if self.source_type == 'pdf':
            default_name = os.path.splitext(os.path.basename(self.source_path))[0] + "_marked.pdf"
            filters = "PDF Files (*.pdf)"
        else:
            default_name = os.path.splitext(os.path.basename(self.source_path))[0] + "_marked.png"
            filters = "PNG Image (*.png);;JPG Image (*.jpg)"

        out_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save File", default_name, filters)
        if not out_path: return
        self.perform_save(out_path)

    def perform_save(self, out_path):
        def get_font(size):
            try: return ImageFont.truetype("arial.ttf", size)
            except: return ImageFont.load_default()

        marker_size_px = self.spin_size.value()

        if self.source_type == 'pdf':
            scale = 2.0
            page = self.source_doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            draw = ImageDraw.Draw(base_img)
            for rx, ry, num, ang in self.markers:
                r = int(marker_size_px * scale)
                font = get_font(int(r * 0.9))
                self._pil_draw_balloon(draw, rx, ry, num, ang, base_img.width, base_img.height, r, font)
            
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                base_img.save(tf.name, quality=95)
                new_doc = fitz.open()
                new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(page.rect, filename=tf.name)
                new_doc.save(out_path)
                new_doc.close()
            os.remove(tf.name)
        else:
            base_img = Image.open(self.source_path).convert("RGB")
            draw = ImageDraw.Draw(base_img)
            for rx, ry, num, ang in self.markers:
                r = marker_size_px
                font = get_font(int(r * 0.9))
                self._pil_draw_balloon(draw, rx, ry, num, ang, base_img.width, base_img.height, r, font)
            base_img.save(out_path)
        
        self.status_label.setText(f"Saved to {out_path}")
        QtWidgets.QMessageBox.information(self, "Saved", "File saved successfully.")

    def _pil_draw_balloon(self, draw, rx, ry, num, angle, w, h, r, font):
        tip_x, tip_y = rx * w, ry * h
        tail_len = int(r * 1.2)
        theta = math.radians(angle)
        dx, dy = math.cos(theta), math.sin(theta)
        cx = tip_x - dx * (tail_len + r)
        cy = tip_y - dy * (tail_len + r)
        pdx, pdy = -dy, dx
        tail_w = r * 0.5
        p1 = (tip_x, tip_y)
        p2 = (cx + pdx * tail_w, cy + pdy * tail_w)
        p3 = (cx - pdx * tail_w, cy - pdy * tail_w)
        draw.polygon([p1, p2, p3], fill=(255, 0, 0))
        bbox = [cx-r, cy-r, cx+r, cy+r]
        draw.ellipse(bbox, fill=(255, 255, 255), outline=(255,0,0), width=max(1, int(r/7)))
        try:
            draw.text((cx, cy), str(num), font=font, fill=(0,0,0), anchor="mm")
        except:
            tw, th = draw.textsize(str(num), font=font)
            draw.text((cx-tw/2, cy-th/2), str(num), font=font, fill=(0,0,0))

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())