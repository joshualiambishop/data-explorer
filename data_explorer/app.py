import multiprocessing
import sys
from typing import List, Optional, Sequence

import numpy as np
import PySide6.QtWidgets as widgets
from PySide6.QtCore import Qt, QTimer, Signal, QSignalBlocker, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from data_explorer.docks.array_dock import ArrayDock, OperationPanel


class ArrayViewerApp(widgets.QMainWindow):

    num_array_changed = Signal()

    def __init__(self, arrays: Sequence[np.ndarray], titles: Sequence[str]) -> None:
        super().__init__()
        self._enforced_shape: Optional[tuple[int, int, int]] = None

        self.arrays = arrays
        self.num_frames = arrays[0].shape[0]
        self.docks: List[ArrayDock] = []
        self.dock_instances: dict[str, int] = {}
        self._is_syncing_view: bool = False
        self._init_ui()
        self._register_keyboard_shortcuts()
        self.num_array_changed.connect(self.on_num_array_changed)
        for array, title in zip(arrays, titles):
            self.register_array(array, title)

        self.update_frames(0)
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_frame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _register_keyboard_shortcuts(self) -> None:
        for key, action in [
            (Qt.Key.Key_Space, lambda: (self.play_button.toggle(), self.toggle_play())),  # type: ignore[func-returns-value]
            (
                Qt.Key.Key_Right,
                lambda: self.slider.setValue(
                    min(self.slider.value() + 1, self.num_frames - 1)
                ),
            ),
            (
                Qt.Key.Key_Left,
                lambda: self.slider.setValue(max(self.slider.value() - 1, 0)),
            ),
            (
                Qt.Key.Key_C,
                lambda: self.crosshair_cb.setChecked(not self.crosshair_cb.isChecked()),
            ),
        ]:
            QShortcut(
                QKeySequence(key),
                self,
                context=Qt.ShortcutContext.ApplicationShortcut,
            ).activated.connect(action)

    def _validate_shape_of(self, array: np.ndarray) -> None:
        if self._enforced_shape is None:
            self._enforced_shape = array.shape[-3:]
        if array.shape[-3:] != self._enforced_shape:
            raise ValueError(
                f"Array provided has shape {array.shape}, but it must be same as others ({self._enforced_shape})."
            )

    @Slot(ArrayDock)
    def _sync_view_to(self, dock: ArrayDock) -> None:
        if not self.sync_view_checkbox.isChecked() or self._is_syncing_view:
            return

        self._is_syncing_view = True
        for other_dock in self.docks:
            if other_dock is not dock:
                with QSignalBlocker(other_dock.view_box):
                    other_dock.view_box.setRange(dock.view_box.viewRect())
        self._is_syncing_view = False

    def _add_array(self, array: np.ndarray, title: str, is_derived: bool) -> ArrayDock:
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
        dock.view_box.user_changed_view.connect(
            lambda dock_to_align=dock: self._sync_view_to(dock_to_align)
        )

        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.num_array_changed.emit()
        return dock

    def register_array(self, array: np.ndarray, title: str) -> "ArrayViewerApp":
        self._add_array(array, title, is_derived=False)
        return self

    @Slot()
    def on_num_array_changed(self) -> None:
        has_enough_data = len(self.get_original_docks()) >= 2
        self.operation_panel.setEnabled(has_enough_data)
        self.operation_panel.setToolTip(
            "At least two arrays are required to perform operations"
            if not has_enough_data
            else ""
        )

    @Slot(ArrayDock)
    def _remove_dock(self, dock: ArrayDock) -> None:
        self.docks.remove(dock)
        self.dock_instances[dock.get_title()] -= 1
        self.num_array_changed.emit()

    @Slot(ArrayDock)
    def duplicate_dock(self, dock: ArrayDock) -> None:
        new_dock = self._add_array(
            dock.get_array(), title=dock.get_title(), is_derived=False
        )
        new_dock.image_config_panel.set_config(dock.image_config_panel.get_config())
        new_dock.threshold_panel.set_config(dock.threshold_panel.get_config())

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

        self.play_button: widgets.QPushButton = widgets.QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.clicked.connect(self.toggle_play)

        self.fps_spinner = widgets.QSpinBox()
        self.fps_spinner.setRange(1, 100)
        self.fps_spinner.setValue(20)
        self.fps_spinner.setSuffix(" fps")

        self.crosshair_cb: widgets.QCheckBox = widgets.QCheckBox("Crosshair")
        self.crosshair_cb.setChecked(True)
        self.crosshair_cb.setToolTip("Show/hide the crosshair and value overlays")
        self.crosshair_cb.stateChanged.connect(self.toggle_crosshair_visbility)

        self.frame_spin = widgets.QSpinBox()
        self.frame_spin.setSingleStep(1)
        self.frame_spin.setRange(0, self.num_frames)
        self.frame_spin.setFixedWidth(60)
        self.frame_spin.valueChanged.connect(lambda i: self.slider.setValue(i))

        self.sync_view_checkbox: widgets.QCheckBox = widgets.QCheckBox("Sync view")
        self.sync_view_checkbox.setToolTip("Synchronise pan and zoom across all docks.")
        self.sync_view_checkbox.setChecked(True)

        control_layout = widgets.QVBoxLayout(self.central)
        control_row = widgets.QHBoxLayout()
        control_row.addWidget(widgets.QLabel("Frame:"))
        control_row.addWidget(self.slider)
        control_row.addWidget(self.frame_spin)
        control_row.addWidget(self.play_button)
        control_row.addWidget(widgets.QLabel("FPS:"))
        control_row.addWidget(self.fps_spinner)
        control_row.addWidget(self.crosshair_cb)
        control_row.addWidget(self.sync_view_checkbox)

        control_layout.addLayout(control_row)

        footer = widgets.QWidget()
        footer.setStyleSheet("background-color: #2b2b2b;")

        self.operation_panel: OperationPanel = OperationPanel(self)

        footer_layout = widgets.QVBoxLayout(footer)

        footer_layout.addLayout(control_layout)
        footer_layout.addWidget(self.operation_panel)
        top_level_layout.addWidget(footer)
        self.central.setSizePolicy(
            widgets.QSizePolicy.Policy.Expanding,  # horizontal
            widgets.QSizePolicy.Policy.Fixed,  # vertical
        )
        self.central.setFixedHeight(self.central.sizeHint().height())

    @Slot(Qt.CheckState)
    def toggle_crosshair_visbility(self, state: Qt.CheckState) -> None:
        for dock in self.docks:
            dock.set_crosshair_visbility(state == Qt.CheckState.Checked.value)

    @Slot(int)
    def update_frames(self, frame: int) -> None:
        with QSignalBlocker(self.frame_spin):
            self.frame_spin.setValue(frame)
        for dock in self.docks:
            dock.set_frame(frame)

    def toggle_play(self) -> None:
        if self.play_button.isChecked():
            interval = int(1000 / self.fps_spinner.value())
            self.timer.start(interval)
        else:
            self.timer.stop()

    @Slot()
    def advance_frame(self) -> None:
        frame = (self.slider.value() + 1) % self.num_frames
        self.slider.setValue(frame)

    @Slot(float, float)
    def broadcast_cursor(self, x: float, y: float) -> None:
        for dock in self.docks:
            dock.sync_crosshair(x, y)


def launch_viewer(arrays: Sequence[np.ndarray], titles: Sequence[str]) -> None:
    # reuse a running QApplication if present
    app = widgets.QApplication.instance() or widgets.QApplication(sys.argv)
    viewer = ArrayViewerApp(arrays, titles)
    viewer.setWindowTitle("3D Array Viewer")
    viewer.resize(1200, 800)
    viewer.show()
    # only start exec if we created the app and we’re in a script
    if not app.closingDown() and __name__ == "__main__":
        sys.exit(app.exec())


if __name__ == "__main__":
    a = np.random.randn(100, 64, 128).astype(np.float32).cumsum(0)
    b = np.random.randn(100, 64, 128).astype(np.float32).cumsum(0)
    b[0, 32, 62] = 20
    b[0, 0, 0] = 0
    launch_viewer([a, b], ["Random A", "Random B"])


# To do list


# Lazy/Future Array Support

# Accept either full np.ndarray or Callable[[frame], np.ndarray] via a FrameProvider descriptor.

# Auto‑generate any extra parameter widgets at launch.
