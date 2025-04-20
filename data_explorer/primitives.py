import PySide6.QtWidgets as widgets


def build_double_spinbox(
    min: float,
    max: float,
    default: float,
    decimals: int = 3,
) -> widgets.QDoubleSpinBox:
    widget = widgets.QDoubleSpinBox()
    widget.setRange(min, max)
    widget.setValue(default)
    widget.setDecimals(decimals)
    return widget
