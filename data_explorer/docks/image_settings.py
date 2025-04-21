from typing import Final, NamedTuple
from data_explorer.docks import panel
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, QSignalBlocker
import numpy as np
from contextlib import ExitStack

COLOURMAPS: Final[list[str]] = ["gray", "viridis", "plasma", "inferno", "magma"]


class ImageConfig(NamedTuple):
    cmap: str
    vmin: float
    vmax: float


class ImageConfigurationPanel(panel.BaseDockPanel):
    panel_name = "Image Configuration"

    config_changed = Signal(object)

    def _build_ui(self) -> None:
        parent_array = self._parent_dock.get_array()

        top_level_layout = QtWidgets.QVBoxLayout(self)
        group = QtWidgets.QGroupBox(self.panel_name)
        layout = QtWidgets.QHBoxLayout(group)

        self.cmap_combo_box = QtWidgets.QComboBox()
        self.cmap_combo_box.addItems(COLOURMAPS)

        self.vmin_spinbox = QtWidgets.QDoubleSpinBox()
        self.vmin_spinbox.setRange(np.nanmin(parent_array), np.nanmax(parent_array))
        self.vmin_spinbox.setValue(np.nanpercentile(parent_array, 1))
        self.vmin_spinbox.setDecimals(3)

        self.vmax_spinbox = QtWidgets.QDoubleSpinBox()
        self.vmax_spinbox.setRange(np.nanmin(parent_array), np.nanmax(parent_array))
        self.vmax_spinbox.setValue(np.nanpercentile(parent_array, 99))
        self.vmax_spinbox.setDecimals(3)

        layout.addWidget(QtWidgets.QLabel("Colourmap:"))
        layout.addWidget(self.cmap_combo_box)
        layout.addWidget(QtWidgets.QLabel("Minimum:"))
        layout.addWidget(self.vmin_spinbox)
        layout.addWidget(QtWidgets.QLabel("Maximum:"))
        layout.addWidget(self.vmax_spinbox)

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
        with ExitStack() as stack:
            for widget in (self.cmap_combo_box, self.vmin_spinbox, self.vmax_spinbox):
                stack.enter_context(QSignalBlocker(widget))

            self.cmap_combo_box.setCurrentText(config.cmap)
            self.vmin_spinbox.setValue(config.vmin)
            self.vmax_spinbox.setValue(config.vmax)
