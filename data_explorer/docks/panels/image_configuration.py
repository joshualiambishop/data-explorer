import dataclasses
from typing import Final
from data_explorer.docks.panels import base_panel
from PySide6 import QtWidgets
from PySide6.QtCore import Signal
import numpy as np


COLOURMAPS: Final[list[str]] = ["gray", "viridis", "plasma", "inferno", "magma"]


@dataclasses.dataclass(frozen=True)
class ImageConfig:
    cmap: str
    vmin: float
    vmax: float


class ImageConfigurationPanel(base_panel.BaseDockPanel[ImageConfig]):
    panel_name = "Image Configuration"

    config_changed = Signal(object)

    def _build_ui(self, parent: QtWidgets.QWidget) -> None:
        parent_dock = self.get_parent_dock()
        data_min, data_max = parent_dock.get_array_bounds()

        step_size = parent_dock.get_appropriate_step_size()

        top_level_layout = QtWidgets.QHBoxLayout(parent)

        self.cmap_combo_box = QtWidgets.QComboBox()
        self.cmap_combo_box.addItems(COLOURMAPS)

        self.vmin_spinbox = QtWidgets.QDoubleSpinBox()
        self.vmax_spinbox = QtWidgets.QDoubleSpinBox()

        for spinbox in (self.vmin_spinbox, self.vmax_spinbox):
            spinbox.setDecimals(3)
            spinbox.setSingleStep(step_size)
            spinbox.setRange(-np.inf, np.inf)

        self.vmin_spinbox.setValue(data_min)
        self.vmax_spinbox.setValue(data_max)

        for label, widget in (
            ("Colourmap:", self.cmap_combo_box),
            ("Minimum:", self.vmin_spinbox),
            ("Maximum:", self.vmax_spinbox),
        ):

            top_level_layout.addWidget(QtWidgets.QLabel(label))
            top_level_layout.addWidget(widget)

        self.reset_button = QtWidgets.QPushButton("<>")
        self.reset_button.clicked.connect(self._set_to_data_range)
        top_level_layout.addWidget(self.reset_button)

    def _connect_signals(self) -> None:
        self.vmin_spinbox.valueChanged.connect(self._on_config_changed)
        self.vmax_spinbox.valueChanged.connect(self._on_config_changed)
        self.cmap_combo_box.currentTextChanged.connect(self._on_config_changed)

    def _on_config_changed(self, _: float | str) -> None:
        self.vmin_spinbox.setMaximum(self.vmax_spinbox.value())
        self.vmax_spinbox.setMinimum(self.vmin_spinbox.value())
        self.config_changed.emit(self.get_config())

    def get_config(self) -> ImageConfig:
        return ImageConfig(
            cmap=self.cmap_combo_box.currentText(),
            vmin=self.vmin_spinbox.value(),
            vmax=self.vmax_spinbox.value(),
        )

    def set_config(self, config: ImageConfig) -> None:
        self.cmap_combo_box.setCurrentText(config.cmap)
        self.vmin_spinbox.setValue(config.vmin)
        self.vmax_spinbox.setValue(config.vmax)

    def _set_to_data_range(self) -> None:
        parent_array = self.get_parent_dock().get_array()
        data_vmin = np.nanmin(parent_array)
        data_vmax = np.nanmax(parent_array)
        new_config = ImageConfig(
            cmap=self.get_config().cmap, vmin=data_vmin, vmax=data_vmax
        )
        self.set_config(new_config)
