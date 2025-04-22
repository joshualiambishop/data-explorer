import dataclasses
from typing import Callable, Final, Optional, TYPE_CHECKING
import pyqtgraph as pg  # type: ignore[import-untyped]
import PySide6.QtWidgets as widgets
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QCloseEvent

import numpy as np
from data_explorer.docks.panels.image_configuration import (
    ImageConfig,
    ImageConfigurationPanel,
)
from data_explorer.docks.panels.threshold import ThresholdConfig, ThresholdPanel

if TYPE_CHECKING:
    from data_explorer.app import ArrayViewerApp

BORDER_COLOUR: Final[str] = "y"
COLOURMAPS: Final[list[str]] = ["gray", "viridis", "plasma", "inferno", "magma"]


def _safe_bounds(array: np.ndarray) -> tuple[float, float]:
    masked_array: np.ndarray = np.ma.masked_invalid(array)
    return float(masked_array.min()), float(masked_array.max())


@dataclasses.dataclass
class SimpleOperation:
    description: str
    operator: Optional[str]
    calculation: Callable[[np.ndarray, np.ndarray], np.ndarray]


TWO_PIECE_OPERATIONS: Final[list[SimpleOperation]] = [
    SimpleOperation("Difference", "-", lambda a, b: a - b),
    SimpleOperation("Division", "/", lambda a, b: a / b),
    SimpleOperation("Sum", "+", lambda a, b: a + b),
]


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

        with np.errstate(divide="ignore"):
            new_arr = self.current_op.calculation(a_arr, b_arr)
        if np.isnan(new_arr).any() or np.isinf(new_arr).any():
            widgets.QMessageBox.warning(
                self, "Calcuation warning", "NaNs and/or infinities may be present"
            )

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
        self._array_bounds = _safe_bounds(array)
        self._frame = 0
        self._instance_number = instance_number

        self._current_image_op: Callable[[np.ndarray], np.ndarray] = lambda x: x
        self._previous_colour_config: Optional[ImageConfig] = None
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

    def get_array_bounds(self) -> tuple[float, float]:
        return self._array_bounds

    def get_appropriate_step_size(self) -> float:
        min, max = self.get_array_bounds()
        return (max - min) / 100.0

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
        self.image_config_panel = ImageConfigurationPanel(self)
        self.image_config_panel.config_changed.connect(self._apply_image_config)
        self._apply_image_config(self.image_config_panel.get_config())
        grid.addWidget(self.image_config_panel, 0, 0, 1, 4)

        self.threshold_panel = ThresholdPanel(self)
        self.threshold_panel.threshold_rule_changed.connect(
            self._on_threshold_rule_changed
        )

        grid.addWidget(self.threshold_panel, 2, 0, 1, 3)

        self.reset_view_btn = widgets.QPushButton("Reset View")
        self.reset_view_btn.setToolTip("Reset pan/zoom to show the full image")
        self.reset_view_btn.clicked.connect(self.on_reset_view)
        grid.addWidget(self.reset_view_btn, 1, 0)

        if not self.is_copy:
            self.duplicate_button = widgets.QPushButton("Duplicate")
            self.duplicate_button.clicked.connect(self.on_duplicate_pressed)
            grid.addWidget(self.duplicate_button, 1, 1, 1, 3)

        parent_layout.addLayout(grid)

    def _on_threshold_rule_changed(self, rule: Optional[ThresholdConfig]) -> None:
        if rule is not None:
            if self._previous_colour_config is None:
                self._previous_colour_config = self.image_config_panel.get_config()
            self._current_image_op = rule.threshold_array

            self.image_config_panel.set_config(
                ImageConfig(cmap="gray", vmin=0.0, vmax=1.0)
            )
            self.image_config_panel.setEnabled(False)
            self.image_config_panel.setToolTip(
                "Cannot change while a threshold rule is active."
            )
        else:
            self._current_image_op = lambda x: x
            self.image_config_panel.setEnabled(True)
            self.image_config_panel.setToolTip("")
            if self._previous_colour_config is not None:
                self.image_config_panel.set_config(self._previous_colour_config)
            self._previous_colour_config = None
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
        image = self._current_image_op(self._array[self._frame].T)

        self.image_item.setImage(image)
        self._apply_image_config(self.image_config_panel.get_config())
        self.sync_crosshair(self.crosshair_y.value(), self.crosshair_x.value())

    def _apply_image_config(self, config: ImageConfig) -> None:
        self.image_item.setLookupTable(
            pg.colormap.get(config.cmap, source="matplotlib").getLookupTable(
                alpha=False
            ),
            update=False,
        )
        self.image_item.setLevels((config.vmin, config.vmax), update=True)

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

    def sync_crosshair(self, x: float, y: float) -> None:
        self.crosshair_y.setPos(x)
        self.crosshair_x.setPos(y)

        self.value_text.setPos(x, y)
        self.y_pos_text.setPos(self.view_box.viewRect().right() - 10, y)
        self.x_pos_text.setPos(x, self.view_box.viewRect().top() - 10)

        ix, iy = int(x), int(y)
        try:
            image = self._current_image_op(self._array[self._frame])

            value = image[iy, ix]

        except IndexError:
            value = float("nan")

        self.value_text.setText(f"Value={value:.3f}")
        self.y_pos_text.setText(f"Y={iy}")
        self.x_pos_text.setText(f"X={ix}")
