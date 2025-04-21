import dataclasses
from typing import Final, NamedTuple
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

    def _build_ui(self) -> None:
        parent_array = self._parent_dock.get_array()
        data_min = np.nanmin(parent_array)
        data_max = np.nanmax(parent_array)

        top_level_layout = QtWidgets.QVBoxLayout(self)
        group = QtWidgets.QGroupBox(self.panel_name)
        hbox_layout = QtWidgets.QHBoxLayout(group)

        self.cmap_combo_box = QtWidgets.QComboBox()
        self.cmap_combo_box.addItems(COLOURMAPS)

        self.vmin_spinbox = QtWidgets.QDoubleSpinBox(
            minimum=data_min,
            maximum=data_max,
            decimals=3,
            value=data_min,
        )

        self.vmax_spinbox = QtWidgets.QDoubleSpinBox(
            minimum=data_min,
            maximum=data_max,
            decimals=3,
            value=data_max,
        )

        for label, widget in (
            ("Colourmap:", self.cmap_combo_box),
            ("Minimum:", self.vmin_spinbox),
            ("Maximum:", self.vmax_spinbox),
        ):

            hbox_layout.addWidget(QtWidgets.QLabel(label))
            hbox_layout.addWidget(widget)

        self.reset_button = QtWidgets.QPushButton("<>")
        self.reset_button.pressed.connect(self._set_to_data_range)
        hbox_layout.addWidget(self.reset_button)

        top_level_layout.addWidget(group)

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
        parent_array = self.get_parent_array_dock().get_array()
        data_vmin = np.nanmin(parent_array)
        data_vmax = np.nanmax(parent_array)
        new_config = ImageConfig(
            cmap=self.get_config().cmap, vmin=data_vmin, vmax=data_vmax
        )
        self.set_config(new_config)
