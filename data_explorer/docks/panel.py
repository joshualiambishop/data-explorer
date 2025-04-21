import abc
import PySide6.QtWidgets as widgets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_explorer.docks.array_dock import ArrayDock


class AbstractDockPanel(widgets.QWidget, abc.ABC):
    panel_name: str

    def __init__(self, parent: ArrayDock) -> None:
        super().__init__(parent)
        self._parent_dock = parent
        self._build_ui()
        self._connect_signals()

    @abc.abstractmethod
    def _build_ui(self) -> None: ...

    @abc.abstractmethod
    def _connect_signals(self) -> None: ...
