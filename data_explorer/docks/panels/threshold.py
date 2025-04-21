import dataclasses
from typing import Callable, Final, Optional
from data_explorer.docks.panels import base_panel
from PySide6 import QtWidgets
from PySide6.QtCore import Signal
import numpy as np


@dataclasses.dataclass(frozen=True)
class ThresholdConfig:
    description: str
    threshold: float
    threshold_func: Callable[[np.ndarray, float], np.ndarray]

    def threshold_array(self, array: np.ndarray):
        return self.threshold_func(array, self.threshold)


THRESHOLD_CONFIGS: Final[list[ThresholdConfig]] = [
    ThresholdConfig("Greater than", 0.0, lambda array, threshold: array > threshold),
    ThresholdConfig("Less than", 0.0, lambda array, threshold: array < threshold),
    ThresholdConfig(
        "Greater or equal to", 0.0, lambda array, threshold: array >= threshold
    ),
    ThresholdConfig(
        "Less or equal to", 0.0, lambda array, threshold: array <= threshold
    ),
    ThresholdConfig("Equal to", 0.0, lambda array, threshold: array == threshold),
]


class ThresholdPanel(base_panel.BaseDockPanel[Optional[ThresholdConfig]]):
    panel_name = "Threshold"

    threshold_rule_changed = Signal(object)

    def _build_ui(self) -> None:
        self._base_config: Optional[ThresholdConfig] = None
        parent_array = self.get_parent_array_dock().get_array()
        top_level_layout = QtWidgets.QVBoxLayout(self)

        self.add_threshold_button = QtWidgets.QPushButton("Add thresholding rule")
        self.add_threshold_button.setToolTip(
            "Create a new rule to threshold the image (reversible)"
        )

        top_level_layout.addWidget(self.add_threshold_button)

        self.threshold_form = QtWidgets.QWidget()
        form_layout = QtWidgets.QHBoxLayout(self.threshold_form)

        self.operator_label = QtWidgets.QLabel("")
        self.threshold_spinbox = QtWidgets.QDoubleSpinBox(
            minimum=np.nanmin(parent_array),
            maximum=np.nanmax(parent_array),
            decimals=3,
            value=np.nanpercentile(parent_array, 50),
        )
        self.cancel_threshold_button = QtWidgets.QPushButton("Cancel")

        for widget in (
            self.operator_label,
            self.threshold_spinbox,
            self.cancel_threshold_button,
        ):
            form_layout.addWidget(widget)

        top_level_layout.addWidget(self.threshold_form)
        self.threshold_form.hide()

    def _connect_signals(self) -> None:
        self.add_threshold_button.clicked.connect(self._show_selection_menu)
        self.threshold_spinbox.valueChanged.connect(self._on_threshold_change)
        self.cancel_threshold_button.clicked.connect(self._clear_threshold)

    def _show_selection_menu(self) -> None:
        menu = QtWidgets.QMenu(self, title="Select thresholding operation")
        for config in THRESHOLD_CONFIGS:
            action = menu.addAction(config.description)
            action.triggered.connect(
                lambda _checked, config=config: self._create_threshold_form(config)
            )
        global_position = self.add_threshold_button.mapToGlobal(
            self.add_threshold_button.rect().bottomLeft()
        )
        menu.exec(global_position)

    def _create_threshold_form(self, config: ThresholdConfig) -> None:

        self._base_config = config

        self.operator_label.setText(f"Highlight values {config.description.lower()}")
        self.add_threshold_button.hide()
        self.threshold_form.show()
        self.threshold_rule_changed.emit(
            dataclasses.replace(config, threshold=self.threshold_spinbox.value())
        )

    def _clear_threshold(self) -> None:
        self._base_config = None
        self.threshold_form.hide()
        self.add_threshold_button.show()
        self.threshold_rule_changed.emit(None)

    def get_config(self) -> Optional[ThresholdConfig]:
        if self._base_config is None:
            return None
        return dataclasses.replace(
            self._base_config, threshold=self.threshold_spinbox.value()
        )

    def _on_threshold_change(self) -> None:
        self.threshold_rule_changed.emit(self.get_config())
