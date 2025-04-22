import multiprocessing
import sys
from typing import List, Optional, Sequence

import numpy as np
import PySide6.QtWidgets as widgets
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from data_explorer.docks.array_dock import ArrayDock, OperationPanel


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
