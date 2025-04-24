import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import Signal


class UserSyncViewBox(pg.ViewBox):
    """Only emit events for user requests to change the view (panning and zooming)"""

    user_changed_view = Signal()

    def mouseDragEvent(self, ev, axis=None) -> None:
        super().mouseDragEvent(ev, axis)
        self.user_changed_view.emit()

    def wheelEvent(self, ev, axis=None) -> None:
        super().wheelEvent(ev, axis)
        self.user_changed_view.emit()
