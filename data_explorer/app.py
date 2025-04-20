import dataclasses
import multiprocessing
import sys
from typing import Callable, Final, List, Optional, Sequence

import numpy as np
import pyqtgraph as pg  # type: ignore[import-untyped]
import PySide6.QtWidgets as widgets
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent

from data_explorer import primitives

BORDER_COLOUR: Final[str] = "y"
COLOURMAPS: Final[list[str]] = ["gray", "viridis", "plasma", "inferno", "magma"]


@dataclasses.dataclass
class SimpleOperation:
    description: str
    operator: Optional[str]
    calculation: Callable[[np.ndarray, np.ndarray], np.ndarray]


SIMPLE_OPERATIONS: Final[list[SimpleOperation]] = [
    SimpleOperation("Difference", "-", lambda a, b: a - b),
    SimpleOperation("Division", "/", lambda a, b: a / b),
    SimpleOperation("Sum", "+", lambda a, b: a + b),
]


class OperationDock(widgets.QDockWidget):
    """
    A fixed dock for creating new derived arrays via arithmetic operations
    """

    def __init__(self, parent_app: "ArrayViewerApp") -> None:
        super().__init__("Operations")
        self.parent_app = parent_app
        self.setFeatures(
            widgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
        )  # No closing, no floating

        self._init_ui()

    def _init_ui(self) -> None:
        self.main_widget = widgets.QWidget()
        self.setWidget(self.main_widget)
        layout = widgets.QVBoxLayout(self.main_widget)
        # initial buttons panel
        self.buttons_panel = widgets.QWidget()
        btn_layout = widgets.QVBoxLayout(self.buttons_panel)
        for operation in SIMPLE_OPERATIONS:
            btn = widgets.QPushButton(
                f"Create {operation.description.lower()} operation"
            )
            btn.clicked.connect(
                lambda _checked, operation=operation: self._show_form(operation)
            )
            btn_layout.addWidget(btn)
        layout.addWidget(self.buttons_panel)

        # form panel hidden until needed
        self.form_panel = widgets.QWidget()
        form_layout = widgets.QGridLayout(self.form_panel)
        self.operator_desc_label = widgets.QLabel("")
        self.operator_op_label = widgets.QLabel("")

        self.combo_a = widgets.QComboBox()
        self.combo_b = widgets.QComboBox()
        form_layout.addWidget(self.operator_desc_label, 0, 0)
        form_layout.addWidget(self.combo_a, 0, 1)
        form_layout.addWidget(self.operator_op_label, 0, 2)
        form_layout.addWidget(self.combo_b, 0, 3)
        self.create_btn = widgets.QPushButton("Create")
        self.cancel_btn = widgets.QPushButton("Cancel")
        form_layout.addWidget(self.create_btn, 1, 0)
        form_layout.addWidget(self.cancel_btn, 1, 3)
        layout.addWidget(self.form_panel)
        self.form_panel.hide()

        self.cancel_btn.clicked.connect(self._reset)
        self.create_btn.clicked.connect(self._create)

    def _show_form(self, operation: SimpleOperation) -> None:
        # populate dropdowns with current dock titles
        titles = [dock.get_title() for dock in self.parent_app.get_original_docks()]
        self.combo_a.clear()
        self.combo_a.addItems(titles)
        self.combo_b.clear()
        self.combo_b.addItems(titles)
        self.operator_desc_label.setText(f"Create {operation.description.lower()}:")
        if operation.operator is not None:
            self.operator_op_label.setText(operation.operator)
        self.current_op = operation
        self.buttons_panel.hide()
        self.form_panel.show()

    def _reset(self) -> None:
        self.form_panel.hide()
        self.buttons_panel.show()

    def _create(self) -> None:
        a_title = self.combo_a.currentText()
        b_title = self.combo_b.currentText()
        # find arrays
        a_arr = next(
            d.get_array()
            for d in self.parent_app.get_original_docks()
            if d.get_title() == a_title
        )
        b_arr = next(
            d.get_array()
            for d in self.parent_app.get_original_docks()
            if d.get_title() == b_title
        )

        self.parent_app._add_array(
            array=self.current_op.calculation(a_arr, b_arr),
            title=f"{a_title} {self.current_op.operator} {b_title}",
            can_delete=True,
        )
        self._reset()


class ArrayDock(widgets.QDockWidget):
    # These signals are controlled globally or require synchronisation
    update_cursor = Signal(float, float)
    duplicate = Signal(object)
    closed = Signal(object)

    def __init__(
        self, array: np.ndarray, title: str, copy: int, can_delete: bool
    ) -> None:
        if array.ndim != 3:
            raise ValueError("Must be a 3 dimensional array (time, y, x).")

        super().__init__(title if copy == 1 else title + f" ({copy})")
        self._title = title
        self._array = array
        self.frame = 0
        self._copy = copy

        features = (
            widgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | widgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        if not self.is_original or can_delete:
            features |= widgets.QDockWidget.DockWidgetFeature.DockWidgetClosable

        self.setFeatures(features)
        self._init_ui()
        self.set_frame(0)

    @property
    def is_original(self) -> bool:
        return self._copy == 1

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

        _, height, width = self._array.shape

        border = widgets.QGraphicsRectItem(0, 0, width, height)
        border.setPen(pg.mkPen(BORDER_COLOUR, width=1))
        border.setZValue(0)

        self.view_box.addItem(border)
        self.view_box.setMouseEnabled(x=True, y=True)

        self.crosshair_y = pg.InfiniteLine(angle=90, movable=False, pen="r")
        self.crosshair_x = pg.InfiniteLine(angle=0, movable=False, pen="r")
        self.view_box.addItem(self.crosshair_y, ignoreBounds=True)
        self.view_box.addItem(self.crosshair_x, ignoreBounds=True)

        self._build_control_panel(layout)

        self.value_text = pg.TextItem(color="r", anchor=(0, 1))
        self.value_text.setZValue(2)
        self.view_box.addItem(self.value_text, ignoreBounds=True)

        self.y_pos_text = pg.TextItem(color="r", anchor=(1, 0))
        self.y_pos_text.setZValue(2)
        self.view_box.addItem(self.y_pos_text, ignoreBounds=True)

        self.x_pos_text = pg.TextItem(color="r", anchor=(0, 0))
        self.x_pos_text.setZValue(2)
        self.view_box.addItem(self.x_pos_text, ignoreBounds=True)

        self.layout_widget.scene().sigMouseMoved.connect(self.mouse_moved)
        self.update_cursor.connect(self.sync_crosshair)

    def _build_control_panel(self, parent_layout: widgets.QVBoxLayout) -> None:

        grid = widgets.QGridLayout()

        self.vmin_spin = primitives.build_double_spinbox(
            min=np.nanmin(self._array),
            max=np.nanmax(self._array),
            default=np.nanpercentile(self._array, 1),
        )
        self.vmin_spin.valueChanged.connect(self.update_clim)

        self.vmax_spin = primitives.build_double_spinbox(
            min=np.nanmin(self._array),
            max=np.nanmax(self._array),
            default=np.nanpercentile(self._array, 99),
        )
        self.vmax_spin.valueChanged.connect(self.update_clim)

        self.cmap_combo = widgets.QComboBox()
        self.cmap_combo.addItems(COLOURMAPS)
        self.cmap_combo.currentTextChanged.connect(self.update_colormap)

        self.reset_view_btn = widgets.QPushButton("Reset View")
        self.reset_view_btn.setToolTip("Reset pan/zoom to show the full image")
        self.reset_view_btn.clicked.connect(self.on_reset_view)

        grid.addWidget(widgets.QLabel("Min:"), 0, 2)
        grid.addWidget(self.vmin_spin, 0, 3)
        grid.addWidget(widgets.QLabel("Max:"), 1, 2)
        grid.addWidget(self.vmax_spin, 1, 3)
        grid.addWidget(widgets.QLabel("Colormap:"), 0, 0)
        grid.addWidget(self.cmap_combo, 0, 1)
        grid.addWidget(self.reset_view_btn, 1, 0)

        # Duplicate button
        if self.is_original:
            self.duplicate_button = widgets.QPushButton("Duplicate")
            self.duplicate_button.clicked.connect(self.on_duplicate_pressed)
            grid.addWidget(self.duplicate_button, 2, 0, 1, 4)

        # Add grid to the layout
        parent_layout.addLayout(grid)

    def get_title(self) -> str:
        return self._title

    def get_array(self) -> np.ndarray:
        return self._array

    def on_duplicate_pressed(self) -> None:
        self.duplicate.emit(self)

    def on_reset_view(self) -> None:
        self.view_box.autoRange()

    def set_crosshair_visbility(self, visible: bool) -> None:
        for item in (
            self.crosshair_x,
            self.crosshair_y,
            self.value_text,
            self.x_pos_text,
            self.y_pos_text,
        ):
            item.setVisible(visible)

    def closeEvent(self, event: QCloseEvent) -> None:
        # We must send a signal out on destruction to close any references.
        self.closed.emit(self)
        super().closeEvent(event)

    def set_frame(self, frame: int) -> None:
        self.frame = frame
        self.image_item.setImage(self._array[self.frame].T)
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
                        0, np.subtract(self._array.shape[1:][::-1], 1)
                    )  # within bounds of data
                    .astype(int)
                    + 0.5  # convert back to image terms
                )
            )

    def update_colormap(self, name: str) -> None:
        self.image_item.setLookupTable(
            pg.colormap.get(name, source="matplotlib").getLookupTable(alpha=False)
        )

    def sync_crosshair(self, x: float, y: float) -> None:
        self.crosshair_y.setPos(x)
        self.crosshair_x.setPos(y)

        self.value_text.setPos(x, y)
        self.y_pos_text.setPos(self.view_box.viewRect().right() - 10, y)
        self.x_pos_text.setPos(x, self.view_box.viewRect().top() - 10)

        ix, iy = int(x), int(y)
        try:
            value = self._array[self.frame, iy, ix]
        except IndexError:
            value = float("nan")

        self.value_text.setText(f"Value={value:.3f}")
        self.y_pos_text.setText(f"Y={iy}")
        self.x_pos_text.setText(f"X={ix}")


class ArrayViewerApp(widgets.QMainWindow):

    def __init__(self, arrays: Sequence[np.ndarray], titles: Sequence[str]) -> None:
        super().__init__()
        self._enforced_shape: Optional[tuple[int, int, int]] = None

        self.arrays = arrays
        self.num_frames = arrays[0].shape[0]
        self.docks: List[ArrayDock] = []
        self.dock_instances: dict[str, int] = {}
        self.frame_label = widgets.QLabel()
        self._init_ui()

        for array, title in zip(arrays, titles):
            self.register_array(array, title)

        self.update_frames(0)
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_frame)
        self.operation_dock = OperationDock(self)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.operation_dock)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _validate_shape_of(self, array: np.ndarray) -> None:
        if self._enforced_shape is None:
            self._enforced_shape = array.shape[-3:]
        if array.shape[-3:] != self._enforced_shape:
            raise ValueError(
                f"Array provided has shape {array.shape}, but it must be same as others ({self._enforced_shape})."
            )

    def _add_array(self, array: np.ndarray, title: str, can_delete: bool) -> None:
        self._validate_shape_of(array)
        self.dock_instances[title] = copy = self.dock_instances.get(title, 0) + 1
        dock = ArrayDock(array=array, title=title, copy=copy, can_delete=can_delete)

        # track instance
        self.docks.append(dock)

        # global signals
        dock.update_cursor.connect(self.broadcast_cursor)
        dock.duplicate.connect(self.duplicate_dock)
        dock.closed.connect(self._remove_dock)

        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)

    def register_array(self, array: np.ndarray, title: str) -> "ArrayViewerApp":
        self._add_array(array, title, can_delete=False)
        return self

    def _remove_dock(self, dock: ArrayDock) -> None:
        if dock.is_original:
            raise ValueError("Can only remove duplicate docks.")
        self.docks.remove(dock)
        self.dock_instances[dock.get_title()] -= 1

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
        self._add_array(dock.get_array(), title=dock.get_title(), can_delete=False)

    def get_original_docks(self) -> list[ArrayDock]:
        return [dock for dock in self.docks if dock.is_original]

    def _init_ui(self) -> None:
        self.setDockNestingEnabled(True)
        self.central = widgets.QWidget()
        self.setCentralWidget(self.central)

        layout = widgets.QVBoxLayout()
        self.central.setLayout(layout)

        self.slider = widgets.QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self.num_frames - 1)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.valueChanged.connect(self.update_frames)

        self.play_button = widgets.QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.clicked.connect(self.toggle_play)

        self.fps_spinner = widgets.QSpinBox()
        self.fps_spinner.setRange(1, 100)
        self.fps_spinner.setValue(20)
        self.fps_spinner.setSuffix(" fps")

        self.crosshair_cb = widgets.QCheckBox("Crosshair")
        self.crosshair_cb.setChecked(True)
        self.crosshair_cb.setToolTip("Show/hide the crosshair and value overlays")
        self.crosshair_cb.stateChanged.connect(self.toggle_crosshair_visbility)

        control_row = widgets.QHBoxLayout()
        control_row.addWidget(widgets.QLabel("Frame:"))
        control_row.addWidget(self.slider)
        control_row.addWidget(self.frame_label)
        control_row.addWidget(self.play_button)
        control_row.addWidget(widgets.QLabel("FPS:"))
        control_row.addWidget(self.fps_spinner)
        control_row.addWidget(self.crosshair_cb)

        layout.addLayout(control_row)

    def toggle_crosshair_visbility(self, state: Qt.CheckState) -> None:
        for dock in self.docks:
            dock.set_crosshair_visbility(state == Qt.CheckState.Checked.value)

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
