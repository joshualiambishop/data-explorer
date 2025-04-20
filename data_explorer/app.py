import dataclasses
import multiprocessing
import sys
from typing import Callable, Final, List, Optional, Sequence

import numpy as np
import pyqtgraph as pg  # type: ignore[import-untyped]
import PySide6.QtWidgets as widgets
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
import numpy.typing as npt
from data_explorer import primitives

BORDER_COLOUR: Final[str] = "y"
COLOURMAPS: Final[list[str]] = ["gray", "viridis", "plasma", "inferno", "magma"]


@dataclasses.dataclass
class SimpleOperation:
    description: str
    operator: Optional[str]
    calculation: Callable[[np.ndarray, np.ndarray], np.ndarray]


@dataclasses.dataclass
class ThresholdOperation:
    description: str
    operator: Optional[str]
    calculation: Callable[[np.ndarray, float], np.ndarray]


TWO_PIECE_OPERATIONS: Final[list[SimpleOperation]] = [
    SimpleOperation("Difference", "-", lambda a, b: a - b),
    SimpleOperation("Division", "/", lambda a, b: a / b),
    SimpleOperation("Sum", "+", lambda a, b: a + b),
]
THRESHOLD_OPERATIONS: Final[list[ThresholdOperation]] = [
    ThresholdOperation("Greater than", ">", lambda array, threshold: array > threshold),
    ThresholdOperation("Less than", "<", lambda array, threshold: array < threshold),
    ThresholdOperation(
        "Greater or equal to", ">=", lambda array, threshold: array >= threshold
    ),
    ThresholdOperation(
        "Less or equal to", "<=", lambda array, threshold: array <= threshold
    ),
    ThresholdOperation("Equal to", "==", lambda array, threshold: array == threshold),
]
_IDENTITY: Final[ThresholdOperation] = ThresholdOperation(
    "IDENTITY", "-", lambda array, threshold: array
)


class OperationPanel(widgets.QWidget):
    """
    A panel for creating new derived arrays through simple operations
    """

    def __init__(self, parent_app: "ArrayViewerApp") -> None:
        super().__init__()
        self.parent_app = parent_app

        layout = widgets.QVBoxLayout(self)

        # initial buttons panel
        self.buttons_panel = widgets.QGroupBox()
        btn_layout = widgets.QHBoxLayout(self.buttons_panel)
        for operation in TWO_PIECE_OPERATIONS:
            btn = widgets.QPushButton(
                f"Calculate {operation.description.lower()} of two arrays"
            )
            btn.clicked.connect(
                lambda _checked, operation=operation: self._show_form(operation)
            )
            btn_layout.addWidget(btn)
        layout.addWidget(self.buttons_panel)

        # form panel hidden until needed
        self.form_panel = widgets.QWidget()
        form_layout = widgets.QHBoxLayout(self.form_panel)
        self.operator_desc_label = widgets.QLabel("")
        self.combo_a = widgets.QComboBox()
        self.operator_op_label = widgets.QLabel("")
        self.combo_b = widgets.QComboBox()

        self.create_btn = widgets.QPushButton("Create")
        self.cancel_btn = widgets.QPushButton("Cancel")
        form_layout.addWidget(self.operator_desc_label)
        form_layout.addWidget(
            self.combo_a, alignment=Qt.AlignmentFlag.AlignRight, stretch=2
        )
        form_layout.addWidget(
            self.operator_op_label, alignment=Qt.AlignmentFlag.AlignCenter, stretch=0
        )
        form_layout.addWidget(
            self.combo_b, alignment=Qt.AlignmentFlag.AlignLeft, stretch=2
        )
        form_layout.addWidget(self.create_btn)
        form_layout.addWidget(self.cancel_btn)
        layout.addWidget(self.form_panel)
        self.form_panel.hide()

        self.cancel_btn.clicked.connect(self._reset)
        self.create_btn.clicked.connect(self._create)
        self.combo_a.currentTextChanged.connect(self._filter_combo_b)

    def _show_form(self, operation: SimpleOperation) -> None:

        titles = [dock.get_title() for dock in self.parent_app.get_original_docks()]
        self.combo_a.clear()
        self.combo_a.addItems(titles)
        # combo b filled in by combo_a signal
        self.operator_desc_label.setText(f"Create {operation.description.lower()}: ")
        self.operator_op_label.setText(operation.operator or "")
        self.current_op = operation
        self.buttons_panel.hide()
        self.form_panel.show()

    def _filter_combo_b(self, selected_title: str) -> None:
        available_titles = [
            title
            for dock in self.parent_app.get_original_docks()
            if (title := dock.get_title()) != selected_title
        ]

        current = self.combo_b.currentText()
        self.combo_b.clear()
        self.combo_b.addItems(available_titles)
        if current in available_titles:
            self.combo_b.setCurrentText(current)

    def _reset(self) -> None:
        self.form_panel.hide()
        self.buttons_panel.show()

    def _create(self) -> None:
        a_title = self.combo_a.currentText()
        b_title = self.combo_b.currentText()
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
        try:
            with np.errstate(divide="raise", invalid="raise"):
                new_arr = self.current_op.calculation(a_arr, b_arr)
            if np.isnan(new_arr).any() or np.isinf(new_arr).any():
                raise FloatingPointError("Result contains NaNs or infinities.")
        except FloatingPointError as e:
            widgets.QMessageBox.warning(self, "Calculation error", str(e))
            return
        new_title = f"{a_title} {self.current_op.operator} {b_title}"
        self.parent_app._add_array(array=new_arr, title=new_title, is_derived=True)
        self._reset()


class ArrayDock(widgets.QDockWidget):
    """
    The ArrayDock is the base widget that can be dragged, duplicated, and is the core of the visualisation.

    Each dock is tightly coupled to raw data, it can spawn duplicates, but the original cannot be closed.

    There is internal logic to apply custom rules for displaying the image; like thresholding.

    There are some parent communication for properly synchronising information across ArrayDock instances, for a unified cursor.
    """

    # These signals are controlled globally or require synchronisation
    update_cursor_signal = Signal(float, float)
    create_duplicate_signal = Signal(object)
    close_signal = Signal(object)

    def __init__(
        self, array: np.ndarray, title: str, instance_number: int, is_derived: bool
    ) -> None:
        if array.ndim != 3:
            raise ValueError("Must be a 3 dimensional array (time, y, x).")

        super().__init__(
            title if instance_number == 1 else title + f" ({instance_number})"
        )
        self._title = title
        self._array = array
        self._frame = 0
        self._instance_number = instance_number

        self._current_threshold_op: Optional[ThresholdOperation] = None
        self._colour_cache: tuple[str, float, float] = ("", 0, 0)
        self.is_derived = is_derived

        features = (
            widgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | widgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        if self.is_copy or self.is_derived:
            features |= widgets.QDockWidget.DockWidgetFeature.DockWidgetClosable

        self.setFeatures(features)
        self._init_ui()
        self.set_frame(0)

    def get_title(self) -> str:
        return self._title

    def get_array(self) -> np.ndarray:
        return self._array

    @property
    def is_copy(self) -> bool:
        return self._instance_number > 1

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
        self.update_cursor_signal.connect(self.sync_crosshair)

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

        colour_group = widgets.QGroupBox("Colour settings")
        cg_layout = widgets.QHBoxLayout(colour_group)

        cg_layout.addWidget(widgets.QLabel("Colormap:"))
        cg_layout.addWidget(self.cmap_combo)
        cg_layout.addWidget(widgets.QLabel("Min:"))
        cg_layout.addWidget(self.vmin_spin)
        cg_layout.addWidget(widgets.QLabel("Max:"))
        cg_layout.addWidget(self.vmax_spin)

        grid.addWidget(colour_group, 0, 0, 1, 4)

        self.new_threshold_button = widgets.QPushButton("Add threshold")
        self.new_threshold_button.setToolTip(
            "Create a new rule to threshold the image (reversible)"
        )
        self.new_threshold_button.clicked.connect(self._show_threshold_menu)
        grid.addWidget(self.new_threshold_button, 2, 0, 1, 3)

        # 2.5.b: Threshold form (hidden until operation chosen)
        self.threshold_form = widgets.QWidget()
        tf_layout = widgets.QHBoxLayout(self.threshold_form)
        self.threshold_desc_label = widgets.QLabel("")

        self.threshold_value_spin = primitives.build_double_spinbox(
            min=np.nanmin(self._array),
            max=np.nanmax(self._array),
            default=np.nanpercentile(self._array, 50),
        )
        self.threshold_cancel_btn = widgets.QPushButton("Cancel")
        tf_layout.addWidget(widgets.QLabel("Threshold values "))
        tf_layout.addWidget(self.threshold_desc_label)
        tf_layout.addWidget(self.threshold_value_spin)
        tf_layout.addWidget(self.threshold_cancel_btn)

        grid.addWidget(self.threshold_form, 2, 0, 1, 3)
        self.threshold_form.hide()

        self.threshold_cancel_btn.clicked.connect(self._cancel_threshold)
        self.threshold_value_spin.valueChanged.connect(
            lambda: self.set_frame(self._frame)
        )

        self.reset_view_btn = widgets.QPushButton("Reset View")
        self.reset_view_btn.setToolTip("Reset pan/zoom to show the full image")
        self.reset_view_btn.clicked.connect(self.on_reset_view)
        grid.addWidget(self.reset_view_btn, 1, 0)

        if not self.is_copy:
            self.duplicate_button = widgets.QPushButton("Duplicate")
            self.duplicate_button.clicked.connect(self.on_duplicate_pressed)
            grid.addWidget(self.duplicate_button, 1, 1, 1, 3)

        parent_layout.addLayout(grid)

    def _show_threshold_menu(self) -> None:
        menu = widgets.QMenu(self, title="Threshold operation")
        for operation in THRESHOLD_OPERATIONS:
            action = menu.addAction(operation.description)
            action.triggered.connect(
                lambda checked, op=operation: self._show_threshold_form(op)
            )
        global_position = self.new_threshold_button.mapToGlobal(
            self.new_threshold_button.rect().bottomLeft()
        )
        menu.exec(global_position)

    def _show_threshold_form(self, operation: ThresholdOperation) -> None:
        self._colour_cache = (
            self.cmap_combo.currentText(),
            self.vmin_spin.value(),
            self.vmax_spin.value(),
        )

        self.vmin_spin.setValue(0)
        self.vmax_spin.setValue(1)
        self.cmap_combo.setCurrentText("gray")

        for widget in (self.vmin_spin, self.vmax_spin, self.cmap_combo):
            widget.setEnabled(False)
            widget.setToolTip("Cannot change while a threshold rule is active.")

        self.threshold_desc_label.setText(operation.description.lower())
        self._current_threshold_op = operation
        self.new_threshold_button.hide()
        self.threshold_form.show()
        self.set_frame(self._frame)

    def _cancel_threshold(self) -> None:
        old_cmap, old_vmin, old_vmax = self._colour_cache
        for widget in (self.vmin_spin, self.vmax_spin, self.cmap_combo):
            widget.setEnabled(True)
            widget.setToolTip("")

        self.vmin_spin.setValue(old_vmin)
        self.vmax_spin.setValue(old_vmax)
        self.cmap_combo.setCurrentText(old_cmap)

        self._current_threshold_op = None
        self.threshold_form.hide()
        self.new_threshold_button.show()
        self.set_frame(self._frame)

    def on_duplicate_pressed(self) -> None:
        self.create_duplicate_signal.emit(self)

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
        self.close_signal.emit(self)
        super().closeEvent(event)

    def set_frame(self, frame: int) -> None:
        self._frame = frame
        image = self._array[self._frame].T
        if self._current_threshold_op is not None:
            threshold = self.threshold_value_spin.value()
            image = self._current_threshold_op.calculation(image, threshold)

        self.image_item.setImage(image)
        self.update_clim()
        self.sync_crosshair(self.crosshair_y.value(), self.crosshair_x.value())

    def update_clim(self) -> None:
        self.image_item.setLevels((self.vmin_spin.value(), self.vmax_spin.value()))
        self.vmax_spin.setMinimum(self.vmin_spin.value())
        self.vmin_spin.setMaximum(self.vmax_spin.value())

    def mouse_moved(self, pos: QPointF) -> None:
        if self.view_box.sceneBoundingRect().contains(pos):
            mouse_point = self.view_box.mapSceneToView(pos)
            self.update_cursor_signal.emit(
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
            image = self._array[self._frame]
            if self._current_threshold_op is not None:
                threshold = self.threshold_value_spin.value()
                image = self._current_threshold_op.calculation(image, threshold)

            value = image[iy, ix]

        except IndexError:
            value = float("nan")

        self.value_text.setText(f"Value={value:.3f}")
        self.y_pos_text.setText(f"Y={iy}")
        self.x_pos_text.setText(f"X={ix}")


class ArrayViewerApp(widgets.QMainWindow):

    new_array_added = Signal()

    def __init__(self, arrays: Sequence[np.ndarray], titles: Sequence[str]) -> None:
        super().__init__()
        self._enforced_shape: Optional[tuple[int, int, int]] = None

        self.arrays = arrays
        self.num_frames = arrays[0].shape[0]
        self.docks: List[ArrayDock] = []
        self.dock_instances: dict[str, int] = {}
        self.frame_label = widgets.QLabel()
        self._init_ui()

        self.new_array_added.connect(self.on_new_array_added)
        for array, title in zip(arrays, titles):
            self.register_array(array, title)

        self.update_frames(0)
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_frame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _validate_shape_of(self, array: np.ndarray) -> None:
        if self._enforced_shape is None:
            self._enforced_shape = array.shape[-3:]
        if array.shape[-3:] != self._enforced_shape:
            raise ValueError(
                f"Array provided has shape {array.shape}, but it must be same as others ({self._enforced_shape})."
            )

    def _add_array(self, array: np.ndarray, title: str, is_derived: bool) -> None:
        self._validate_shape_of(array)
        self.dock_instances[title] = self.dock_instances.get(title, 0) + 1
        dock = ArrayDock(
            array=array,
            title=title,
            instance_number=self.dock_instances[title],
            is_derived=is_derived,
        )

        # track instance
        self.docks.append(dock)

        # global signals
        dock.update_cursor_signal.connect(self.broadcast_cursor)
        dock.create_duplicate_signal.connect(self.duplicate_dock)
        dock.close_signal.connect(self._remove_dock)

        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.new_array_added.emit()

    def register_array(self, array: np.ndarray, title: str) -> "ArrayViewerApp":
        self._add_array(array, title, is_derived=False)
        return self

    def on_new_array_added(self) -> None:
        has_enough_data = len(self.get_original_docks()) >= 2
        self.operation_panel.setEnabled(has_enough_data)
        self.operation_panel.setToolTip(
            "At least two arrays are required to perform operations"
            if not has_enough_data
            else ""
        )

    def _remove_dock(self, dock: ArrayDock) -> None:
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

        elif key_pressed == Qt.Key.Key_C:
            self.crosshair_cb.setChecked(not self.crosshair_cb.isChecked())

        else:
            super().keyPressEvent(event)

    def duplicate_dock(self, dock: ArrayDock) -> None:
        self._add_array(dock.get_array(), title=dock.get_title(), is_derived=False)

    def get_original_docks(self) -> list[ArrayDock]:
        return [dock for dock in self.docks if not dock.is_copy]

    def _init_ui(self) -> None:
        self.setDockNestingEnabled(True)
        self.central = widgets.QWidget()
        self.setCentralWidget(self.central)

        top_level_layout = widgets.QVBoxLayout()
        top_level_layout.setContentsMargins(0, 0, 0, 0)
        top_level_layout.setSpacing(0)
        self.central.setLayout(top_level_layout)

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

        control_layout = widgets.QVBoxLayout(self.central)
        control_row = widgets.QHBoxLayout()
        control_row.addWidget(widgets.QLabel("Frame:"))
        control_row.addWidget(self.slider)
        control_row.addWidget(self.frame_label)
        control_row.addWidget(self.play_button)
        control_row.addWidget(widgets.QLabel("FPS:"))
        control_row.addWidget(self.fps_spinner)
        control_row.addWidget(self.crosshair_cb)

        control_layout.addLayout(control_row)

        footer = widgets.QWidget()
        footer.setStyleSheet("background-color: #2b2b2b;")

        self.operation_panel = OperationPanel(self)

        footer_layout = widgets.QVBoxLayout(footer)

        footer_layout.addLayout(control_layout)
        footer_layout.addWidget(self.operation_panel)

        top_level_layout.addWidget(footer)

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


# To do list


# Lazy/Future Array Support

# Accept either full np.ndarray or Callable[[frame], np.ndarray] via a FrameProvider descriptor.

# Auto‑generate any extra parameter widgets at launch.
