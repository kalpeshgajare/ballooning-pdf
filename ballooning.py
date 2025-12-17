import sys
import tempfile
import fitz  # PyMuPDF
from PyQt5 import QtWidgets, QtGui, QtCore
from PIL import Image, ImageDraw, ImageFont
import os

class Canvas(QtWidgets.QLabel):
    """A QLabel that can display an image and detect mouse clicks to add markers."""
    marker_added = QtCore.pyqtSignal(int, int)

    def __init__(self, qpixmap, scaled_radius):
        super().__init__()
        self.setBackgroundRole(QtGui.QPalette.Base)

        # Dynamic marker properties based on radius passed from MainWindow
        self.circle_radius = scaled_radius
        self.border_thickness = max(1, int(scaled_radius / 7.5))
        self.number_font_size = int(scaled_radius * 0.9)

        self.setPixmap(qpixmap)
        self.setScaledContents(False)
        self.adjustSize()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            pix = self.pixmap()
            if pix is None:
                return

            # Dimensions of actual pixmap
            iw, ih = pix.width(), pix.height()
            # Dimensions of QLabel area
            lw, lh = self.width(), self.height()

            # Centered offset
            offset_x = (lw - iw) // 2
            offset_y = (lh - ih) // 2

            # Convert click from Label coords → Pixmap coords
            x = event.x() - offset_x
            y = event.y() - offset_y

            # Ignore clicks outside image region
            if x < 0 or y < 0 or x > iw or y > ih:
                return

            self.marker_added.emit(int(x), int(y))
            event.accept()
        else:
            super().mousePressEvent(event)

    def draw_marker(self, num, x, y):
        """Draws a single numbered circle marker on the current pixmap."""
        pm = self.pixmap().copy()
        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Draw the circle
        pen = QtGui.QPen(QtGui.QColor(255, 0, 0), self.border_thickness)
        painter.setPen(pen)
        painter.drawEllipse(QtCore.QPoint(x, y), self.circle_radius, self.circle_radius)

        # Draw the number inside the circle
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 0)))
        font = QtGui.QFont("Arial", self.number_font_size, QtGui.QFont.Bold)
        painter.setFont(font)
        rect = QtCore.QRectF(
            x - self.circle_radius,
            y - self.circle_radius,
            self.circle_radius * 2,
            self.circle_radius * 2,
        )
        painter.drawText(rect, QtCore.Qt.AlignCenter, str(num))
        painter.end()
        self.setPixmap(pm)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF & Image Marker Tool")
        self.resize(1200, 800)

        self.source_path = None
        self.source_type = None
        self.source_doc = None
        self.original_dims = None

        self.markers = []
        self.undone_markers = []
        self.marker_count = 0
        self.zoom_level = 1.0
        self.zoom_step = 0.25
        self.marker_radius = 30

        container = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(container)
        self.setCentralWidget(container)
        self.setup_toolbar()

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.vbox.addWidget(self.scroll)

        self.placeholder_label = QtWidgets.QLabel("Open a PDF or Image file to start.")
        self.placeholder_label.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll.setWidget(self.placeholder_label)

    def setup_toolbar(self):
        toolbar = QtWidgets.QHBoxLayout()
        open_btn = QtWidgets.QPushButton("Open File")
        save_btn = QtWidgets.QPushButton("Save File")
        clear_btn = QtWidgets.QPushButton("Clear Markers")
        undo_btn = QtWidgets.QPushButton("Undo")
        redo_btn = QtWidgets.QPushButton("Redo")
        zoom_in_btn = QtWidgets.QPushButton("Zoom In (+)")
        zoom_out_btn = QtWidgets.QPushButton("Zoom Out (-)")
        self.zoom_label = QtWidgets.QLabel()

        size_label = QtWidgets.QLabel("Marker Size:")
        self.size_spinbox = QtWidgets.QSpinBox()
        self.size_spinbox.setMinimum(5)
        self.size_spinbox.setMaximum(100)
        self.size_spinbox.setValue(self.marker_radius)
        self.size_spinbox.setSuffix(" px")
        self.size_spinbox.valueChanged.connect(self.update_marker_size)

        open_btn.clicked.connect(self.open_file)
        save_btn.clicked.connect(self.save_file)
        clear_btn.clicked.connect(self.clear_all_markers)
        undo_btn.clicked.connect(self.undo_marker)
        redo_btn.clicked.connect(self.redo_marker)
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_out_btn.clicked.connect(self.zoom_out)

        toolbar.addWidget(open_btn)
        toolbar.addWidget(save_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addSpacing(20)
        toolbar.addWidget(undo_btn)
        toolbar.addWidget(redo_btn)
        toolbar.addSpacing(20)
        toolbar.addWidget(zoom_out_btn)
        toolbar.addWidget(zoom_in_btn)
        toolbar.addWidget(self.zoom_label)
        toolbar.addSpacing(20)
        toolbar.addWidget(size_label)
        toolbar.addWidget(self.size_spinbox)
        toolbar.addStretch()

        self.vbox.addLayout(toolbar)
        self.update_zoom_label()

    def open_file(self):
        file_filter = "All Supported Files (*.pdf *.png *.jpg *.jpeg *.bmp);;PDF Files (*.pdf);;Image Files (*.png *.jpg *.jpeg *.bmp)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open File", "", file_filter)
        if not path:
            return

        self.clear_all_markers()
        self.source_path = path

        if path.lower().endswith(".pdf"):
            self.source_doc = fitz.open(path)
            self.source_type = 'pdf'
            page = self.source_doc.load_page(0)
            self.original_dims = (page.rect.width, page.rect.height)
        else:
            pixmap = QtGui.QPixmap(path)
            if pixmap.isNull():
                return
            self.source_type = 'image'
            self.source_doc = None
            self.original_dims = (pixmap.width(), pixmap.height())

        self.display_source()

    def display_source(self):
        if self.source_type == 'pdf':
            page = self.source_doc.load_page(0)
            mat = fitz.Matrix(self.zoom_level, self.zoom_level)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            qimg = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888)
            qpix = QtGui.QPixmap.fromImage(qimg)
        else:
            original_pixmap = QtGui.QPixmap(self.source_path)
            new_width = int(self.original_dims[0] * self.zoom_level)
            new_height = int(self.original_dims[1] * self.zoom_level)
            qpix = original_pixmap.scaled(new_width, new_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        scaled_radius = int(self.marker_radius * self.zoom_level)
        canvas = Canvas(qpix, scaled_radius)
        canvas.marker_added.connect(self.add_marker)
        self.scroll.setWidget(canvas)

        self.redraw_all_markers()
        self.update_zoom_label()

    def update_marker_size(self, value):
        self.marker_radius = value
        if self.source_path:
            self.display_source()

    def zoom_in(self):
        self.zoom_level += self.zoom_step
        self.display_source()

    def zoom_out(self):
        if self.zoom_level - self.zoom_step >= 0.25:
            self.zoom_level -= self.zoom_step
            self.display_source()

    def update_zoom_label(self):
        self.zoom_label.setText(f"Zoom: {int(self.zoom_level * 100)}%")

    def add_marker(self, x, y):
        canvas = self.scroll.widget()
        rel_x = x / canvas.pixmap().width()
        rel_y = y / canvas.pixmap().height()

        self.marker_count += 1
        self.markers.append((rel_x, rel_y, self.marker_count))
        self.undone_markers.clear()

        canvas.draw_marker(self.marker_count, x, y)

    def redraw_all_markers(self):
        canvas = self.scroll.widget()
        pixmap_width = canvas.pixmap().width()
        pixmap_height = canvas.pixmap().height()
        for rel_x, rel_y, num in self.markers:
            abs_x = int(rel_x * pixmap_width)
            abs_y = int(rel_y * pixmap_height)
            canvas.draw_marker(num, abs_x, abs_y)

    def undo_marker(self):
        if self.markers:
            self.undone_markers.append(self.markers.pop())
            self.display_source()

    def redo_marker(self):
        if self.undone_markers:
            self.markers.append(self.undone_markers.pop())
            self.display_source()

    def clear_all_markers(self):
        self.markers.clear()
        self.undone_markers.clear()
        self.marker_count = 0
        if self.source_path:
            self.display_source()

    def _find_available_font(self):
        font_candidates = ['arial.ttf', 'calibri.ttf', 'verdana.ttf', 'DejaVuSans.ttf', 'LiberationSans-Regular.ttf']
        for font_name in font_candidates:
            try:
                ImageFont.truetype(font_name, size=10)
                return font_name
            except IOError:
                continue
        return None

    def save_file(self):
        if not self.source_path:
            return
        if not self.markers:
            return

        if self.source_type == 'pdf':
            default_name = os.path.splitext(os.path.basename(self.source_path))[0] + "_marked.pdf"
            file_filter = "PDF Files (*.pdf)"
        else:
            default_name = os.path.splitext(os.path.basename(self.source_path))[0] + "_marked.png"
            file_filter = "PNG Image (*.png);;JPG Image (*.jpg)"

        out_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save File", default_name, file_filter)
        if not out_path:
            return

        font_path = self._find_available_font()
        font_loader = (lambda size: ImageFont.truetype(font_path, size)) if font_path else ImageFont.load_default

        if self.source_type == 'pdf':
            self.save_as_pdf(out_path, font_loader)
        else:
            self.save_as_image(out_path, font_loader)

        QtWidgets.QMessageBox.information(self, "Saved", f"Marked file saved to:\n{out_path}")

    def save_as_pdf(self, out_path, font_loader):
        high_res_zoom = 3.0
        page = self.source_doc.load_page(0)
        mat = fitz.Matrix(high_res_zoom, high_res_zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        draw = ImageDraw.Draw(base_img)

        for rel_x, rel_y, num in self.markers:
            radius = int(self.marker_radius * high_res_zoom)
            border_width = max(1, int(radius / 7.5))
            font_size = int(radius * 0.9)
            font = font_loader(font_size)

            cx = int(rel_x * pix.width)
            cy = int(rel_y * pix.height)

            draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], outline=(255,0,0), width=border_width)
            draw.text((cx, cy), str(num), font=font, fill=(255,0,0), anchor="mm")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_img:
            base_img.save(temp_img.name)
            new_doc = fitz.open()
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, filename=temp_img.name)
            new_doc.save(out_path)
            new_doc.close()
        os.remove(temp_img.name)

    def save_as_image(self, out_path, font_loader):
        base_img = Image.open(self.source_path).convert("RGB")
        draw = ImageDraw.Draw(base_img)

        for rel_x, rel_y, num in self.markers:
            radius = self.marker_radius
            border_width = max(1, int(radius / 7.5))
            font_size = int(radius * 0.9)
            font = font_loader(font_size)

            cx = int(rel_x * base_img.width)
            cy = int(rel_y * base_img.height)

            draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], outline=(255,0,0), width=border_width)
            draw.text((cx, cy), str(num), font=font, fill=(255,0,0), anchor="mm")

        base_img.save(out_path)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
