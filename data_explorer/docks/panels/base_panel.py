import PySide6.QtWidgets as widgets
from typing import TYPE_CHECKING, TypeVar, Generic

if TYPE_CHECKING:
    from data_explorer.docks.array_dock import ArrayDock


Config_T = TypeVar("Config_T")


class BaseDockPanel(widgets.QWidget, Generic[Config_T]):
    panel_name: str

    def __init__(self, parent: "ArrayDock") -> None:
        super().__init__(parent)
        self._parent_dock = parent
        self._build_ui()
        self._connect_signals()

    def get_parent_array_dock(self) -> "ArrayDock":
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
