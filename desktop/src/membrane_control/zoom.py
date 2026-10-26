"""Native Qt interface zoom, always derived from immutable 100% dimensions.

Only display geometry and fonts are changed. Plot data, values, recipe fields
and controller communication are deliberately outside this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QPen
from PySide6.QtWidgets import QFormLayout, QGridLayout, QHeaderView, QLayout, QSplitter, QTableWidget, QWidget
from shiboken6 import isValid


_DIMENSION = re.compile(r"(?<![\w.#])(-?\d+(?:\.\d+)?)(px|pt)\b")
_UNLIMITED = 16777215


def scaled_stylesheet(source: str, factor: float) -> str:
    """Scale dimensions, leaving colors, percentages and font weights alone."""
    if factor == 1:
        return source
    def dimension(match):
        value = float(match[1]) * factor
        if match[2] == "px" and value > 0:
            value = max(1, value)  # Keep thin native borders visible when reduced.
        return f"{value:g}{match[2]}"
    return _DIMENSION.sub(dimension, source)


def _font(source: QFont, factor: float) -> QFont:
    font = QFont(source)
    if font.pointSizeF() > 0:
        font.setPointSizeF(max(1.0, source.pointSizeF() * factor))
    elif font.pixelSize() > 0:
        font.setPixelSize(max(1, round(source.pixelSize() * factor)))
    return font


@dataclass
class _Widget:
    font: QFont
    minimum: QSize
    maximum: QSize
    stylesheet: str
    icon_size: QSize | None
    handle_width: int | None
    last_stylesheet: str | None = None


class NativeZoom:
    MIN_PERCENT = 60
    MAX_PERCENT = 150
    STEP_PERCENT = 10

    def __init__(self, root: QWidget, plots=()):
        self.root = root
        self.percent = 100
        self.widgets: dict[QWidget, _Widget] = {}
        self.layouts: dict[QLayout, dict] = {}
        self.tables: dict[QTableWidget, dict] = {}
        self.plots = [self._plot_state(plot) for plot in plots]
        self._capture_tree(root, new=False)

    @property
    def factor(self) -> float:
        return self.percent / 100

    def _prune(self):
        # QTableWidget deletes cell widgets on replacement. Strong references
        # keep stable Python identities while live; invalid C++ wrappers must
        # never be revisited and are removed on every registration/apply.
        self.widgets = {widget: state for widget, state in self.widgets.items() if isValid(widget)}
        self.layouts = {layout: state for layout, state in self.layouts.items() if isValid(layout)}
        self.tables = {table: state for table, state in self.tables.items() if isValid(table)}

    def _capture_tree(self, parent: QWidget, new: bool):
        self._prune()
        for widget in [parent, *parent.findChildren(QWidget)]:
            if widget in self.widgets:
                continue
            widget.ensurePolished()
            base_font = QFont(widget.font())
            # Newly created cells inherit the already-scaled parent stylesheet.
            if new and self.factor != 1:
                base_font = _font(base_font, 1 / self.factor)
            icon = QSize(widget.iconSize()) if callable(getattr(widget, "iconSize", None)) else None
            self.widgets[widget] = _Widget(base_font, QSize(widget.minimumSize()), QSize(widget.maximumSize()),
                widget.styleSheet(), icon, widget.handleWidth() if isinstance(widget, QSplitter) else None)
            if isinstance(widget, QTableWidget):
                vertical, horizontal = widget.verticalHeader(), widget.horizontalHeader()
                self.tables[widget] = {
                    "row_default": vertical.defaultSectionSize(),
                    "row_min": vertical.minimumSectionSize(),
                    "column_min": horizontal.minimumSectionSize(),
                    "columns": {index: widget.columnWidth(index) for index in range(widget.columnCount())
                                if horizontal.sectionResizeMode(index) == QHeaderView.ResizeMode.Fixed},
                }
        for layout in parent.findChildren(QLayout):
            if layout in self.layouts:
                continue
            margins = layout.contentsMargins()
            spacing = layout.spacing()
            spacers = []
            for index in range(layout.count()):
                spacer = layout.itemAt(index).spacerItem()
                if spacer is not None:
                    spacers.append((spacer, spacer.sizeHint(), spacer.sizePolicy()))
            state = {"margins": (margins.left(), margins.top(), margins.right(), margins.bottom()),
                     "spacing": spacing, "spacers": spacers}
            if isinstance(layout, (QGridLayout, QFormLayout)):
                state["horizontal"] = layout.horizontalSpacing()
                state["vertical"] = layout.verticalSpacing()
            self.layouts[layout] = state

    def register_tree(self, parent: QWidget):
        """Register newly added native controls, then apply the current zoom."""
        self._capture_tree(parent, new=True)
        if self.percent != 100:
            self._apply()

    def set_stylesheet(self, widget: QWidget, source: str):
        """Dynamic colors still use unscaled source CSS on every update."""
        if widget not in self.widgets:
            self._capture_tree(widget, new=True)
        state = self.widgets[widget]
        state.stylesheet = source
        self._style(widget, state)

    def _style(self, widget, state):
        rendered = scaled_stylesheet(state.stylesheet, self.factor)
        if state.last_stylesheet != rendered:
            widget.setStyleSheet(rendered)
            state.last_stylesheet = rendered

    def set_percent(self, percent: int):
        value = max(self.MIN_PERCENT, min(self.MAX_PERCENT, int(percent)))
        value = round(value / self.STEP_PERCENT) * self.STEP_PERCENT
        if value == self.percent:
            return
        self.percent = value
        self._apply()

    @staticmethod
    def _dimension(value, factor):
        return value if value >= _UNLIMITED else max(0, round(value * factor))

    def _apply(self):
        self._prune()
        factor = self.factor
        outer_size = self.root.size()
        self.root.setUpdatesEnabled(False)
        try:
            self._style(self.root, self.widgets[self.root])
            for widget, state in self.widgets.items():
                self._style(widget, state)
                widget.setFont(_font(state.font, factor))
                if widget is self.root:
                    continue
                widget.setMinimumSize(self._dimension(state.minimum.width(), factor), self._dimension(state.minimum.height(), factor))
                widget.setMaximumSize(self._dimension(state.maximum.width(), factor), self._dimension(state.maximum.height(), factor))
                if state.icon_size is not None:
                    widget.setIconSize(QSize(max(1, round(state.icon_size.width() * factor)), max(1, round(state.icon_size.height() * factor))))
                if state.handle_width is not None:
                    widget.setHandleWidth(max(1, round(state.handle_width * factor)))
            for layout, state in self.layouts.items():
                layout.setContentsMargins(*(round(value * factor) for value in state["margins"]))
                # -1 means native style spacing. Use its baseline six logical
                # pixels while zoomed, restoring native inheritance on reset.
                spacing = state["spacing"]
                layout.setSpacing(spacing if factor == 1 else round((6 if spacing < 0 else spacing) * factor))
                if "horizontal" in state:
                    for direction in ("horizontal", "vertical"):
                        value = state[direction]
                        scaled = value if factor == 1 else round((6 if value < 0 else value) * factor)
                        getattr(layout, "set" + direction.capitalize() + "Spacing")(scaled)
                for spacer, size, policy in state["spacers"]:
                    if isValid(spacer):
                        spacer.changeSize(round(size.width() * factor), round(size.height() * factor),
                                          policy.horizontalPolicy(), policy.verticalPolicy())
                layout.invalidate()
            for table, state in self.tables.items():
                vertical, horizontal = table.verticalHeader(), table.horizontalHeader()
                vertical.setMinimumSectionSize(max(1, round(state["row_min"] * factor)))
                horizontal.setMinimumSectionSize(max(1, round(state["column_min"] * factor)))
                height = max(1, round(state["row_default"] * factor))
                vertical.setDefaultSectionSize(height)
                for row in range(table.rowCount()):
                    table.setRowHeight(row, height)
                for column, width in state["columns"].items():
                    table.setColumnWidth(column, max(1, round(width * factor)))
            for state in self.plots:
                self._scale_plot(state, factor)
            base = self.widgets[self.root].minimum
            # Zoom must not resize the outer window. Below 100%, lower the
            # laptop minimum; above/reset, do not force a smaller existing
            # window to grow. Its content can scroll at larger factors.
            self.root.setMinimumSize(min(outer_size.width(), round(base.width() * min(factor, 1))),
                                     min(outer_size.height(), round(base.height() * min(factor, 1))))
            self.root.updateGeometry()
            if self.root.layout():
                self.root.layout().activate()
        finally:
            self.root.setUpdatesEnabled(True)
            self.root.update()

    @staticmethod
    def _plot_state(plot):
        item = plot.getPlotItem()
        margins = item.layout.getContentsMargins()
        axes = []
        for name in ("left", "bottom"):
            axis = item.getAxis(name)
            tick_font = axis.style["tickFont"]
            axes.append({"axis": axis, "tick_font": QFont(tick_font) if tick_font else None,
                "fallback_font": QFont(plot.font()), "label_font": QFont(axis.label.font()),
                "label_style": dict(axis.labelStyle), "text": axis.labelText, "units": axis.labelUnits,
                "prefix": axis.labelUnitPrefix, "power": axis.unitPower,
                "offset": axis.style["tickTextOffset"][0 if name == "left" else 1],
                "tick_length": axis.style["tickLength"], "text_width": axis.style["tickTextWidth"],
                "text_height": axis.style["tickTextHeight"],
                # Before the scene's first layout, width() can still report its
                # old geometry. setWidth() records the requested fixed width
                # in the minimum/maximum pair immediately.
                "width": (axis.minimumWidth() if axis.minimumWidth() == axis.maximumWidth()
                          else axis.width()) if name == "left" else None})
        return {"plot": plot, "title": item.titleLabel.text, "title_options": dict(item.titleLabel.opts),
                "title_minimum": item.titleLabel.minimumHeight(), "title_maximum": item.titleLabel.maximumHeight(),
                "margins": margins, "horizontal": item.layout.horizontalSpacing(), "vertical": item.layout.verticalSpacing(),
                "title_height": item.layout.rowMinimumHeight(0), "axes": axes,
                "curves": [(curve, QPen(curve.opts["pen"])) for curve in item.listDataItems() if curve.opts.get("pen") is not None]}

    @staticmethod
    def _scale_plot(state, factor):
        plot = state["plot"]
        if not isValid(plot):
            return
        item = plot.getPlotItem()
        options = dict(state["title_options"])
        if "size" in options:
            options["size"] = scaled_stylesheet(options["size"], factor)
        item.titleLabel.setText(state["title"], **options)
        item.titleLabel.setMinimumHeight(state["title_minimum"] * factor)
        item.titleLabel.setMaximumHeight(state["title_maximum"] * factor)
        item.layout.setContentsMargins(*(value * factor for value in state["margins"]))
        item.layout.setHorizontalSpacing(state["horizontal"] * factor)
        item.layout.setVerticalSpacing(state["vertical"] * factor)
        item.layout.setRowFixedHeight(0, state["title_height"] * factor)
        for data in state["axes"]:
            axis = data["axis"]
            tick_font = data["tick_font"] if factor == 1 else _font(data["tick_font"] or data["fallback_font"], factor)
            axis.setStyle(tickFont=tick_font, tickTextOffset=round(data["offset"] * factor),
                          tickLength=round(data["tick_length"] * factor), tickTextWidth=round(data["text_width"] * factor),
                          tickTextHeight=round(data["text_height"] * factor))
            axis.label.setFont(_font(data["label_font"], factor))
            styles = {key: scaled_stylesheet(value, factor) if isinstance(value, str) else value
                      for key, value in data["label_style"].items()}
            axis.setLabel(text=data["text"], units=data["units"], unitPrefix=data["prefix"], unitPower=data["power"], **styles)
            if data["width"] is not None:
                axis.setWidth(data["width"] * factor)
        for curve, source in state["curves"]:
            if isValid(curve):
                pen = QPen(source)
                pen.setWidthF(source.widthF() * factor)
                curve.setPen(pen)
        item.layout.invalidate()
        item.layout.activate()
