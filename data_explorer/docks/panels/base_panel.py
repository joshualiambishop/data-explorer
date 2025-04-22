from PySide6 import QtWidgets
from typing import TYPE_CHECKING, TypeVar, Generic
from PySide6.QtCore import Signal

if TYPE_CHECKING:
    from data_explorer.docks.array_dock import ArrayDock


Config_T = TypeVar("Config_T")


class BaseDockPanel(QtWidgets.QWidget, Generic[Config_T]):

    panel_name: str

    def __init__(self, parent_dock: "ArrayDock") -> None:
        super().__init__(parent_dock)
        self._parent_dock = parent_dock

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        label = QtWidgets.QLabel(self.panel_name)
        label.setStyleSheet("font-weight: bold;")
        header.addWidget(label, stretch=1)

        self._build_ui()
        self._connect_signals()

    def get_parent_dock(self) -> "ArrayDock":
        return self._parent_dock

    def _build_ui(self) -> None:
        """For neateness, a method for building the UI elements only."""
        raise NotImplementedError()

    def _connect_signals(self) -> None:
        """For neatness, a method for connecting signals up"""
        raise NotImplementedError()

    def get_config(self) -> Config_T:
        """Get method for copy and pasting / duplicating configs"""
        raise NotImplementedError()

    def set_config(self, config: Config_T) -> None:
        """Set method for copy and pasting / duplicating configs"""
        raise NotImplementedError()
