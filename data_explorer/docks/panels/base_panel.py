from PySide6 import QtWidgets
from typing import TYPE_CHECKING, Any, TypeVar, Generic
from PySide6.QtCore import Slot, Qt, Signal

if TYPE_CHECKING:
    from data_explorer.docks.array_dock import ArrayDock


Config_T = TypeVar("Config_T")


class BaseDockPanel(QtWidgets.QGroupBox, Generic[Config_T]):

    PANEL_REGISTRY: dict[str, type["BaseDockPanel[Any]"]] = {}

    """
    Base class for panels that live under an ArrayDock.

    Panels may represent data transformations tool, or extra
    visualisations that are inherently tethered to a single piece of data.

    The base class implements the general master format, which includes a place
    for the panel itself to live, and buttons for copy and paste to transfer
    configurations easily to other docks.
    """

    panel_name: str
    copy_requested = Signal(object)  # self
    paste_requested = Signal(object)  # self

    def __init_subclass__(cls: type["BaseDockPanel[Config_T]"], **kwargs: Any) -> None:
        super(BaseDockPanel, cls).__init_subclass__(**kwargs)

        # Can't mix in abc.ABC with QWidgets so this will have to do...
        for func_name in ("_build_ui", "_connect_signals", "get_config", "set_config"):
            if getattr(cls, func_name) is getattr(BaseDockPanel, func_name):
                raise TypeError(f"{cls.__name__} must override `{func_name}()`")

        if not hasattr(cls, "panel_name") or not isinstance(cls.panel_name, str):
            raise TypeError(f"{cls.__name__}.panel_name must be a string")

        BaseDockPanel.PANEL_REGISTRY[cls.panel_name] = cls

    def __init__(self, parent_dock: "ArrayDock") -> None:
        super().__init__(
            title=self.panel_name,
            parent=parent_dock,
            checkable=True,  # used for open/closed
            checked=False,  # start closed
            flat=True,  # don't show the border
        )
        self._parent_dock = parent_dock
        self._current_visbility = False

        main_layout = QtWidgets.QHBoxLayout(self)
        self.toggled.connect(self.set_visibility)

        # Body to be overridden by subclasses
        self._panel_body = QtWidgets.QWidget(self)
        main_layout.addWidget(self._panel_body, stretch=1)
        self._build_ui(self._panel_body)

        self._copy_button = QtWidgets.QPushButton("⧉")
        self._copy_button.clicked.connect(lambda *_: self.copy_requested.emit(self))
        self._paste_button = QtWidgets.QPushButton("⇩")
        self._paste_button.clicked.connect(lambda *_: self.paste_requested.emit(self))

        self._buttons = QtWidgets.QWidget()
        button_layout = QtWidgets.QVBoxLayout(self._buttons)

        for button in (
            self._copy_button,
            self._paste_button,
        ):
            # button.setFixedSize(20, 20)
            button_layout.addWidget(
                button, stretch=0, alignment=Qt.AlignmentFlag.AlignRight
            )

        main_layout.addWidget(
            self._buttons,
        )

        self._connect_signals()
        self.set_visibility(False)

    def get_parent_dock(self) -> "ArrayDock":
        return self._parent_dock

    @Slot(bool)
    def set_visibility(self, visible: bool) -> None:
        self._buttons.setVisible(visible)
        self._panel_body.setVisible(visible)
        self.setFlat(not visible)
        self._current_visbility = visible

    def get_visbility(self) -> bool:
        return self._current_visbility

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
