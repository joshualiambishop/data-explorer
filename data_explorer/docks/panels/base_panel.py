from PySide6 import QtWidgets
from typing import TYPE_CHECKING, TypeVar, Generic
from PySide6.QtCore import Signal, Qt

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

        self._toggle_button = QtWidgets.QToolButton()
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(False)
        self._toggle_button.setArrowType(Qt.ArrowType.RightArrow)

        label = QtWidgets.QLabel(self.panel_name)

        self._copy_button = QtWidgets.QPushButton("⧉")
        self._paste_button = QtWidgets.QPushButton("⇩")

        header.addWidget(self._toggle_button)
        header.addWidget(label, stretch=1)
        for button in (
            self._copy_button,
            self._paste_button,
        ):
            button.setFixedSize(20, 20)
            header.addWidget(button, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)

        # Body to be overridden by subclasses
        self._panel_body = QtWidgets.QWidget(self)
        self._panel_body.setVisible(False)

        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(2)
        main.addLayout(header)
        main.addWidget(self._panel_body)

        self._toggle_button.toggled.connect(self.on_toggle_visbility)

        self._build_ui(self._panel_body)

        self._connect_signals()

    def get_parent_dock(self) -> "ArrayDock":
        return self._parent_dock

    def on_toggle_visbility(self, visible: bool) -> None:
        self._panel_body.setVisible(visible)
        self._toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )

    def _build_ui(self, parent: QtWidgets.QWidget) -> None:
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
