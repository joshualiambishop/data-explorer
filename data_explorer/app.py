import multiprocessing
import sys
from typing import Final, List

import numpy as np
import pyqtgraph as pg
import PySide6.QtWidgets as widgets
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent

BORDER_COLOUR: Final[str] = "y"


class ArrayDock(widgets.QDockWidget):
    update_cursor = Signal(float, float)
    duplicate = Signal(object)
    closed = Signal(object)

    def __init__(
        self, title: str, data: np.ndarray, is_duplicate: bool = False
    ) -> None:

        if data.ndim != 3:
            raise ValueError("Must be a 3 dimensional array (time, y, x).")

        super().__init__(title)
        self._title = title
        self._data = data
        self.frame = 0
        self.is_duplicate = is_duplicate

        features = (
            widgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | widgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        if self.is_duplicate:
            features |= widgets.QDockWidget.DockWidgetFeature.DockWidgetClosable

        self.setFeatures(features)
        self._init_ui()
        self.set_frame(0)

    def _init_ui(self) -> None:

        self.main_widget = widgets.QWidget()
        self.setWidget(self.main_widget)

        self.layout_widget = pg.GraphicsLayoutWidget()
        layout = widgets.QVBoxLayout()
        layout.addWidget(self.layout_widget)
        self.main_widget.setLayout(layout)

        self.image_item = pg.ImageItem()

        self.view_box = self.layout_widget.ci.addViewBox(lockAspect=True)
        self.view_box.addItem(self.image_item)

        _, height, width = self._data.shape

        border = widgets.QGraphicsRectItem(0, 0, width, height)
        border.setPen(pg.mkPen(BORDER_COLOUR, width=1))
        border.setZValue(0)

        self.view_box.addItem(border)
        self.view_box.setMouseEnabled(x=True, y=True)

        self.crosshair_y = pg.InfiniteLine(angle=90, movable=False, pen="r")
        self.crosshair_x = pg.InfiniteLine(angle=0, movable=False, pen="r")
        self.view_box.addItem(self.crosshair_y, ignoreBounds=True)
        self.view_box.addItem(self.crosshair_x, ignoreBounds=True)

        control_layout = widgets.QFormLayout()

        self.value_text = pg.TextItem(color="r", anchor=(0, 1))
        self.value_text.setZValue(2)
        self.view_box.addItem(self.value_text, ignoreBounds=True)

        self.y_pos_text = pg.TextItem(color="r", anchor=(1, 0))
        self.y_pos_text.setZValue(2)
        self.view_box.addItem(self.y_pos_text, ignoreBounds=True)

        self.x_pos_text = pg.TextItem(color="r", anchor=(0, 0))
        self.x_pos_text.setZValue(2)
        self.view_box.addItem(self.x_pos_text, ignoreBounds=True)

        self.vmin_spin = widgets.QDoubleSpinBox()
        self.vmin_spin.setDecimals(3)
        self.vmin_spin.setRange(float(self._data.min()), float(self._data.max()))
        self.vmin_spin.setValue(float(np.percentile(self._data, 1)))
        self.vmin_spin.valueChanged.connect(self.update_clim)
        control_layout.addRow("Min:", self.vmin_spin)

        self.vmax_spin = widgets.QDoubleSpinBox()
        self.vmax_spin.setDecimals(3)
        self.vmax_spin.setRange(float(np.min(self._data)), float(np.max(self._data)))
        self.vmax_spin.setValue(float(np.percentile(self._data, 99)))
        self.vmax_spin.valueChanged.connect(self.update_clim)
        control_layout.addRow("Max:", self.vmax_spin)

        self.cmap_combo = widgets.QComboBox()
        self.cmap_combo.addItems(["gray", "viridis", "plasma", "inferno", "magma"])
        self.cmap_combo.setCurrentText("gray")
        self.cmap_combo.currentTextChanged.connect(self.update_colormap)
        control_layout.addRow("Colourmap:", self.cmap_combo)

        self.reset_view_btn = widgets.QPushButton("Reset View")
        self.reset_view_btn.setToolTip("Reset pan/zoom to show the full image")
        self.reset_view_btn.clicked.connect(self.on_reset_view)
        control_layout.addRow(self.reset_view_btn)

        self.crosshair_cb = widgets.QCheckBox("Crosshair")
        self.crosshair_cb.setChecked(True)
        self.crosshair_cb.setToolTip("Show/hide the crosshair and value overlays")
        self.crosshair_cb.checkStateChanged.connect(self.on_toggle_crosshair)
        control_layout.addRow(self.crosshair_cb)

        if not self.is_duplicate:
            self.duplicate_button = widgets.QPushButton("Duplicate")
            self.duplicate_button.clicked.connect(self.on_duplicate_pressed)
            control_layout.addRow(self.duplicate_button)

        layout.addLayout(control_layout)

        self.layout_widget.scene().sigMouseMoved.connect(self.mouse_moved)
        self.update_cursor.connect(self.sync_crosshair)

    def get_title(self) -> str:
        return self._title

    def get_data(self) -> np.ndarray:
        return self._data

    def on_duplicate_pressed(self) -> None:
        self.duplicate.emit(self)

    def on_reset_view(self) -> None:
        self.view_box.autoRange()

    def on_toggle_crosshair(self, state: Qt.CheckState) -> None:
        for item in (
            self.crosshair_x,
            self.crosshair_y,
            self.value_text,
            self.x_pos_text,
            self.y_pos_text,
        ):
            item.setVisible(state is Qt.CheckState.Checked)

    def closeEvent(self, event: QCloseEvent) -> None:
        # We must send a signal out on destruction to close any references.
        self.closed.emit(self)
        super().closeEvent(event)

    def set_frame(self, frame: int) -> None:
        self.frame = frame
        self.image_item.setImage(self._data[self.frame].T)
        self.update_clim()
        self.sync_crosshair(self.crosshair_y.value(), self.crosshair_x.value())

    def update_clim(self) -> None:
        self.image_item.setLevels((self.vmin_spin.value(), self.vmax_spin.value()))
        self.vmax_spin.setMinimum(self.vmin_spin.value())
        self.vmin_spin.setMaximum(self.vmax_spin.value())

    def mouse_moved(self, pos: QPointF) -> None:
        if self.view_box.sceneBoundingRect().contains(pos):
            mouse_point = self.view_box.mapSceneToView(pos)
            self.update_cursor.emit(
                *(
                    np.subtract(
                        [mouse_point.x(), mouse_point.y()], 0.5
                    )  # convert to centre-alignment
                    .round()  # find closest pixel
                    .clip(
                        0, np.subtract(self._data.shape[1:][::-1], 1)
                    )  # within bounds of data
                    .astype(int)
                    + 0.5  # convert back to image terms
                )
            )

    def update_colormap(self, name: str) -> None:
        self.image_item.setLookupTable(
            pg.colormap.get(name).getLookupTable(alpha=False)
        )

    def sync_crosshair(self, x: float, y: float) -> None:
        self.crosshair_y.setPos(x)
        self.crosshair_x.setPos(y)

        self.value_text.setPos(x, y)
        self.y_pos_text.setPos(self.view_box.viewRect().right() - 10, y)
        self.x_pos_text.setPos(x, self.view_box.viewRect().top() - 10)

        ix, iy = int(x), int(y)
        if 0 <= iy < self._data.shape[1] and 0 <= ix < self._data.shape[2]:
            value = self._data[self.frame, iy, ix]
        else:
            value = float("nan")

        self.value_text.setText(f"Value={value:.3f}")
        self.y_pos_text.setText(f"Y={iy}")
        self.x_pos_text.setText(f"X={ix}")


class ArrayViewerApp(widgets.QMainWindow):
    def __init__(self, arrays: List[np.ndarray], titles: List[str]) -> None:
        super().__init__()
        assert all(
            arr.shape == arrays[0].shape for arr in arrays
        ), "All arrays must have the same shape"

        self.arrays = arrays
        self.num_frames = arrays[0].shape[0]
        self.docks: List[ArrayDock] = []
        self.frame_label = widgets.QLabel()

        self._init_ui()

        self.update_frames(0)

        for array, title in zip(arrays, titles):
            dock = ArrayDock(title, array)
            dock.update_cursor.connect(self.broadcast_cursor)
            dock.duplicate.connect(self.duplicate_dock)
            dock.closed.connect(self.remove_dock)
            self.docks.append(dock)
            self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)

        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_frame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event: QKeyEvent) -> None:

        key_pressed = event.key()
        if key_pressed == Qt.Key.Key_Space:
            self.play_button.toggle()
            self.toggle_play()
        elif key_pressed == Qt.Key.Key_Right:
            # next frame
            self.slider.setValue(min(self.slider.value() + 1, self.num_frames - 1))
        elif key_pressed == Qt.Key.Key_Left:
            # previous frame
            self.slider.setValue(max(self.slider.value() - 1, 0))
        else:
            super().keyPressEvent(event)

    def duplicate_dock(self, dock: ArrayDock) -> None:
        clone = ArrayDock(
            title=dock.get_title() + " (Duplicate)",
            data=dock.get_data(),
            is_duplicate=True,
        )
        clone.set_frame(dock.frame)

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, clone)
        clone.update_cursor.connect(self.broadcast_cursor)
        self.docks.append(clone)

    def remove_dock(self, dock: ArrayDock) -> None:
        if not dock.is_duplicate:
            raise ValueError("Can only remove duplicate docks.")
        self.docks.remove(dock)

    def _init_ui(self) -> None:
        self.central = widgets.QWidget()
        self.setCentralWidget(self.central)

        layout = widgets.QVBoxLayout()
        self.central.setLayout(layout)

        self.slider = widgets.QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self.num_frames - 1)
        self.slider.valueChanged.connect(self.update_frames)

        self.play_button = widgets.QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.clicked.connect(self.toggle_play)

        self.fps_spinner = widgets.QSpinBox()
        self.fps_spinner.setRange(1, 100)
        self.fps_spinner.setValue(20)
        self.fps_spinner.setSuffix(" fps")

        control_row = widgets.QHBoxLayout()
        control_row.addWidget(widgets.QLabel("Frame:"))
        control_row.addWidget(self.slider)
        control_row.addWidget(self.frame_label)
        control_row.addWidget(self.play_button)
        control_row.addWidget(widgets.QLabel("FPS:"))
        control_row.addWidget(self.fps_spinner)

        layout.addLayout(control_row)

    def update_frames(self, frame: int) -> None:
        self.frame_label.setText(f"{frame+1}/{self.num_frames}")
        for dock in self.docks:
            dock.set_frame(frame)

    def toggle_play(self) -> None:
        if self.play_button.isChecked():
            interval = int(1000 / self.fps_spinner.value())
            self.timer.start(interval)
        else:
            self.timer.stop()

    def advance_frame(self) -> None:
        frame = (self.slider.value() + 1) % self.num_frames
        self.slider.setValue(frame)

    def broadcast_cursor(self, x: float, y: float) -> None:
        for dock in self.docks:
            dock.sync_crosshair(x, y)


def _launch_viewer(arrays: List[np.ndarray], titles: List[str]) -> None:
    app = widgets.QApplication(sys.argv)
    viewer = ArrayViewerApp(
        arrays,
        titles,
    )
    viewer.setWindowTitle("3D Array Viewer")
    viewer.resize(1200, 800)
    viewer.show()
    viewer.setFocus()
    sys.exit(app.exec())


def launch_viewer(arrays: List[np.ndarray], titles: List[str]) -> None:
    if __name__ == "__main__":
        _launch_viewer(arrays, titles)
    else:
        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(target=_launch_viewer, args=(arrays, titles))
        proc.start()


if __name__ == "__main__":
    a = np.random.randn(100, 64, 128).astype(np.float32).cumsum(0)
    b = np.random.randn(100, 64, 128).astype(np.float32).cumsum(0)
    b[0, 32, 62] = 20
    b[0, 0, 0] = -20
    launch_viewer([a, b], ["Random A", "Random B"])
