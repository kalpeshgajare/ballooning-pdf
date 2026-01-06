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
        """
        Saves the file. 
        - If PDF: Draws vector shapes (resolution independent).
        - If Image: Draws high-res raster shapes scaled to image size.
        """
        if self.source_type == 'pdf':
            self._save_pdf_vector(out_path)
        else:
            self._save_image_raster(out_path)

        self.status_label.setText(f"Saved to {out_path}")
        QtWidgets.QMessageBox.information(self, "Saved", "File saved successfully.")

    def _save_pdf_vector(self, out_path):
        """
        Draws markers directly onto the PDF page using PyMuPDF (fitz) vector methods.
        This ensures 100% crisp quality at any zoom level.
        """
        # Create a new handle for the doc to avoid interfering with the open view
        # or just use the existing self.source_doc but save to a new path
        doc = fitz.open(self.source_path)
        page = doc[0]  # Assuming single page for now, or match logic
        
        page_w = page.rect.width
        page_h = page.rect.height

        # Base size from slider
        base_size = self.spin_size.value()
        
        # Define color (PyMuPDF uses 0.0-1.0 float tuples for colors)
        red = (1, 0, 0)
        white = (1, 1, 1)
        black = (0, 0, 0)

        for rx, ry, num, ang in self.markers:
            # Calculate positions
            tip_x = rx * page_w
            tip_y = ry * page_h
            r = base_size # In PDF points, roughly equal to screen pixels
            
            # --- Draw Pointer (Triangle) ---
            tail_len = r * 1.2
            theta = math.radians(ang)
            dx = math.cos(theta)
            dy = math.sin(theta)

            cx = tip_x - dx * (tail_len + r)
            cy = tip_y - dy * (tail_len + r)
            
            # Perpendicular vector for tail width
            pdx, pdy = -dy, dx
            tail_w = r * 0.5
            
            # Triangle points
            p_tip = fitz.Point(tip_x, tip_y)
            p_base1 = fitz.Point(cx + pdx * tail_w, cy + pdy * tail_w)
            p_base2 = fitz.Point(cx - pdx * tail_w, cy - pdy * tail_w)
            
            # Draw filled red triangle (no border needed if filled)
            shape = page.new_shape()
            shape.draw_poly([p_tip, p_base1, p_base2])
            shape.finish(color=red, fill=red, width=0)
            shape.commit()

            # --- Draw Circle ---
            # Draw filled white circle with red border
            shape = page.new_shape()
            shape.draw_circle(fitz.Point(cx, cy), r)
            shape.finish(color=red, fill=white, width=max(1, r/7))
            shape.commit()

            # --- Draw Text ---
            # Insert text centered at (cx, cy)
            # PyMuPDF insert_text anchor is bottom-left usually, or we use text_writer
            font_size = int(r * 0.9) # Slightly larger for PDF clarity
            
            # Text alignment logic
            text_val = str(num)
            
            # We use a TextWriter to center alignment easily
            tw = fitz.TextWriter(page.rect)
            font = fitz.Font("helv") # Standard Helvetica
            
            # Measure text to center it
            text_len = font.text_length(text_val, fontsize=font_size)
            text_x = cx - (text_len / 2)
            text_y = cy + (font_size * 0.35) # Approximate vertical centering
            
            page.insert_text((text_x, text_y), text_val, fontsize=font_size, fontname="helv", color=black)

        doc.save(out_path)
        doc.close()

    def _save_image_raster(self, out_path):
        """
        Saves as PNG/JPG using 4x Super-Sampling with corrected text size.
        """
        print(f"--- SAVING IMAGE TO: {out_path} ---")

        # 1. Load the base image
        base_img = Image.open(self.source_path).convert("RGBA")
        orig_w, orig_h = base_img.size
        
        # 2. Setup Super-Sampling (4x resolution)
        SUPERSAMPLE = 4
        super_w = orig_w * SUPERSAMPLE
        super_h = orig_h * SUPERSAMPLE
        
        # Create a transparent overlay for high-quality drawing
        overlay = Image.new("RGBA", (super_w, super_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        
        # 3. Calculate Sizes
        scale_factor = max(1.0, orig_w / 1000.0)
        user_r = self.spin_size.value()
        final_r = int(user_r * scale_factor * SUPERSAMPLE)

        # --- SIZE FIX IS HERE ---
        # WAS: int(final_r * 1.3)  <-- This was too big
        # NOW: int(final_r * 0.75) <-- This fits perfectly inside the circle
        font_size = int(final_r * 0.9)
        
        print(f"DEBUG: Radius={final_r}, Font Size={font_size}")

        # 4. Load High-Res Font
        font = None
        font_candidates = [
            "arial.ttf", "Arial.ttf", 
            "/Library/Fonts/Arial.ttf", 
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
            "C:\\Windows\\Fonts\\arial.ttf"
        ]
        
        for f_path in font_candidates:
            try:
                font = ImageFont.truetype(f_path, font_size)
                break
            except OSError:
                continue
                
        if font is None:
            print("WARNING: Default font used (Size might look wrong)")
            font = ImageFont.load_default()

        # 5. Draw on the Giant Overlay
        for rx, ry, num, ang in self.markers:
            self._pil_draw_balloon(draw, rx, ry, num, ang, super_w, super_h, final_r, font, 1.0)

        # 6. Shrink Overlay back to Original Size
        overlay_smooth = overlay.resize((orig_w, orig_h), resample=Image.Resampling.LANCZOS)
        
        # 7. Composite and Save
        final_img = Image.alpha_composite(base_img, overlay_smooth)
        final_img.convert("RGB").save(out_path, quality=95)
        print("--- SAVE COMPLETE ---")

    def _pil_draw_balloon(self, draw, rx, ry, num, angle, w, h, r, font, scale):
        """
        Draws the balloon with thin edges but THICK numbers.
        """
        tip_x, tip_y = rx * w, ry * h
        tail_len = int(r * 1.2)
        theta = math.radians(angle)
        dx, dy = math.cos(theta), math.sin(theta)
        
        cx = tip_x - dx * (tail_len + r)
        cy = tip_y - dy * (tail_len + r)
        
        pdx, pdy = -dy, dx
        tail_w = r * 0.5
        
        # 1. CIRCLE THICKNESS (Thinner)
        # Higher number = Thinner line (e.g. 10.0 or 12.0)
        circle_thickness = max(2, int(r / 8.0))
        
        # 2. NUMBER THICKNESS (Thicker)
        # We simulate BOLD by adding a stroke width.
        # Lower number = Thicker text (e.g. r / 20.0 is very bold, r / 40.0 is medium)
        text_stroke = max(1, int(r / 30.0))

        # Draw Tail (Triangle)
        p1 = (tip_x, tip_y)
        p2 = (cx + pdx * tail_w, cy + pdy * tail_w)
        p3 = (cx - pdx * tail_w, cy - pdy * tail_w)
        draw.polygon([p1, p2, p3], fill=(255, 0, 0))
        
        # Draw Circle
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.ellipse(bbox, fill=(255, 255, 255), outline=(255, 0, 0), width=circle_thickness)
        
        # Draw Text
        text_str = str(num)
        try:
            left, top, right, bottom = draw.textbbox((0, 0), text_str, font=font, stroke_width=text_stroke)
            tw = right - left
            th = bottom - top
            # Adjust Y slightly because stroke makes text taller
            text_pos = (cx - tw / 2, cy - th / 2 - (th * 0.1)) 
        except AttributeError:
            tw, th = draw.textsize(text_str, font=font, stroke_width=text_stroke)
            text_pos = (cx - tw / 2, cy - th / 2)

        # Draw text with stroke_width to make it BOLD
        draw.text(text_pos, text_str, font=font, fill=(0, 0, 0), stroke_width=text_stroke, stroke_fill=(0, 0, 0))


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())