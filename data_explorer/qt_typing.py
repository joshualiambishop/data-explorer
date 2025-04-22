from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Generic, Callable, Any, Optional, List, TypeVar

    T = TypeVar("T")

    class Signal(Generic[T]):
        """
        Typing‐only stub for PySide6.QtCore.Signal
        """

        def __init__(
            self,
            *types: type,
            name: Optional[str] = ...,
            arguments: Optional[List[str]] = ...
        ) -> None: ...
        def connect(self, slot: Callable[[T], None]) -> None: ...
        def disconnect(self, slot: Callable[[T], None]) -> None: ...
        def emit(self, arg: T) -> None: ...

else:
    from PySide6.QtCore import Signal
