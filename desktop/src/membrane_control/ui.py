"""Qt desktop interface for the membrane controller.

Device access and experiment execution live in AppController. The UI never
opens serial ports or changes outputs except through an explicit controller
action initiated by the user.
"""
from __future__ import annotations

from collections import deque
import math
import os
from pathlib import Path
import time
from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)
import pyqtgraph as pg

from .models import Recipe, Step


STYLE = """
QMainWindow, QWidget#appRoot { background: #f4f6f8; color: #182b3b; }
QWidget { font-family: 'Segoe UI', Arial; font-size: 10pt; }
QLabel { color: #243746; }
QLabel#appTitle { font-size: 22pt; font-weight: 650; color: #142b3b; }
QLabel#subtitle, QLabel#muted { color: #617482; }
QLabel#metricValue { font-size: 25pt; font-weight: 600; color: #142b3b; }
QLabel#metricUnit { color: #617482; font-size: 9pt; }
QFrame#metricCard { background: white; border: 1px solid #dce4e9; border-radius: 8px; }
QLabel#simulationBanner { color: #79520a; background: #fff5dc; border: 1px solid #ead398; border-radius: 6px; padding: 10px; }
QLabel#hardwareBanner { color: #215265; background: #eaf3f7; border: 1px solid #cbdfe8; border-radius: 6px; padding: 10px; }
QLabel#faultBanner { color: #962f34; background: #fff0f0; border: 1px solid #edc1c3; border-radius: 6px; padding: 9px; }
QLabel#stateChip { background: #e3edf0; border-radius: 12px; color: #295567; padding: 7px 14px; font-weight: 600; }
QTabWidget::pane { background: white; border: 1px solid #dce4e9; border-radius: 6px; }
QTabBar::tab { color: #5a6c79; background: #edf1f4; padding: 11px 19px; margin-right: 3px; border-top-left-radius: 5px; border-top-right-radius: 5px; }
QTabBar::tab:selected { background: white; color: #165e77; font-weight: 600; }
QGroupBox { background: white; border: 1px solid #dce4e9; border-radius: 7px; margin-top: 13px; padding: 15px 12px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #324c5e; }
QPushButton { background: white; border: 1px solid #cbd7df; border-radius: 5px; padding: 7px 13px; color: #243c4d; }
QPushButton:hover { background: #edf5f8; border-color: #8eafbe; }
QPushButton:pressed { background: #daeaf0; }
QPushButton:disabled { color: #92a0aa; background: #f3f5f6; border-color: #e0e5e8; }
QPushButton#primaryButton { background: #176b83; border-color: #176b83; color: white; font-weight: 600; }
QPushButton#primaryButton:hover { background: #12576d; }
QPushButton#primaryButton:disabled { background: #a8bec7; border-color: #a8bec7; }
QPushButton#stopButton { background: #a73e43; border-color: #a73e43; color: white; font-weight: 600; }
QPushButton#stopButton:disabled { background: #dcc3c5; border-color: #dcc3c5; }
QToolButton { background: #f2f5f7; border: 1px solid #cfdbe2; border-radius: 6px; padding: 9px 6px; min-width: 54px; color: #536a7a; }
QToolButton:checked { background: #dceff0; border-color: #388d93; color: #155e65; font-weight: 600; }
QToolButton:disabled { color: #9aa7ae; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit { background: white; color: #243746; border: 1px solid #cbd7df; border-radius: 4px; padding: 5px; selection-background-color: #c5e1ea; }
QComboBox { padding-right: 24px; min-height: 20px; }
QTableWidget { border: 1px solid #dce4e9; background: white; gridline-color: #e5eaee; alternate-background-color: #f6f8fa; }
QHeaderView::section { background: #edf2f5; color: #3c5666; border: 0; border-bottom: 1px solid #dce4e9; padding: 8px 5px; font-weight: 600; }
QTableWidget::item:selected { background: #dcecf2; color: #183b4c; }
QStatusBar { background: #edf1f4; color: #526a78; }
"""


def _label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def _button(text: str, callback, name: str = "") -> QPushButton:
    button = QPushButton(text)
    if name:
        button.setObjectName(name)
    button.clicked.connect(callback)
    return button


def _number(value: Any, precision: int = 2) -> str:
    try:
        number = float(value)
        return f"{number:,.{precision}f}" if math.isfinite(number) else "Waiting"
    except (TypeError, ValueError):
        return "Waiting"


class MainWindow(QMainWindow):
    """Single-window dashboard, recipe editor and device setup."""

    def __init__(self, controller):
        super().__init__()
        # Qt's Windows offscreen plugin does not enumerate system fonts.
        # Register installed fonts for readable automated screenshots without
        # changing normal desktop behavior or shipping third-party font files.
        if not QFontDatabase.families():
            font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for filename in ("segoeui.ttf", "segoeuib.ttf", "segoeuisb.ttf"):
                path = font_dir / filename
                if path.is_file():
                    QFontDatabase.addApplicationFont(str(path))
        self.controller = controller
        self._updating = False
        self._last_log = ""
        self._last_error = ""
        self._last_error_at = 0.0
        self._plot_start = time.monotonic()
        self._last_plot = 0.0
        self._previous_state: str | None = None
        self._timer_fault = ""
        self._timer_stop_requested = False
        self._plot_time: deque[float] = deque(maxlen=600)
        self._plot_data = {key: deque(maxlen=600) for key in ("flow_ml_min", "pressure_psi", "flux_lmh", "mass_g")}
        self._curves: dict[str, Any] = {}
        self._metric_labels: dict[str, QLabel] = {}
        self._presets: dict[str, Recipe] = {}
        self._editor_recipe: Recipe | None = None
        self._history: list[dict] = []
        self.setWindowTitle("Membrane Control")
        self.resize(1360, 940)
        self.setMinimumSize(1080, 760)
        self.setStyleSheet(STYLE)
        pg.setConfigOptions(antialias=True, background="w", foreground="#536b7b")

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 16, 22, 12)
        layout.setSpacing(11)
        self._build_header(layout)
        self.banner = _label("", "simulationBanner", True)
        layout.addWidget(self.banner)
        self.fault_label = _label("", "faultBanner", True)
        self.fault_label.hide()
        fault_row = QHBoxLayout()
        fault_row.addWidget(self.fault_label, 1)
        self.clear_fault_button = _button("Clear fault", self._clear_fault)
        self.clear_fault_button.hide()
        fault_row.addWidget(self.clear_fault_button)
        layout.addLayout(fault_row)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)
        self._build_dashboard()
        self._build_editor()
        self._build_connections()
        self._build_history()
        self.statusBar().showMessage("Ready. Simulation is the default; no hardware connection is opened automatically.")

        self._load_presets()
        current = getattr(controller, "recipe", None)
        if current is not None:
            self._populate_recipe(current)
        elif self._presets:
            self._select_preset(0)
        self._load_settings()
        self._refresh_ports()
        self._refresh_history()
        self._update_view(dict(self.controller.snapshot))
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

    def _build_header(self, layout):
        row = QHBoxLayout()
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(_label("Membrane Control", "appTitle"))
        title.addWidget(_label("Experiment controls, live measurements and recorded runs", "subtitle"))
        row.addLayout(title)
        row.addStretch()
        self.state_chip = _label("IDLE", "stateChip")
        row.addWidget(self.state_chip)
        self.simulation_check = QCheckBox("Simulation mode")
        self.simulation_check.setAccessibleName("Enable simulation mode")
        self.simulation_check.setChecked(True)
        self.simulation_check.toggled.connect(self._toggle_simulation)
        row.addSpacing(12)
        row.addWidget(self.simulation_check)
        layout.addLayout(row)

    def _build_dashboard(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(15, 12, 15, 12)
        outer.setSpacing(10)
        controls = QHBoxLayout()
        controls.addWidget(_label("Preset"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(190)
        self.preset_combo.setAccessibleName("Experiment preset")
        self.preset_combo.currentIndexChanged.connect(self._select_preset)
        controls.addWidget(self.preset_combo)
        self.start_button = _button("Start run", self._start_run, "primaryButton")
        self.stop_button = _button("Stop run", self._stop_run, "stopButton")
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        self.export_current_button = _button("Export CSV", self._export_current)
        controls.addWidget(self.export_current_button)
        controls.addStretch()
        self.controller_badge = _label("Controller: disconnected", "muted")
        self.balance_badge = _label("Balance: disconnected", "muted")
        controls.addWidget(self.controller_badge)
        controls.addSpacing(10)
        controls.addWidget(self.balance_badge)
        outer.addLayout(controls)
        self.run_summary = _label("No run active. Load a demo template or edit a custom sequence.", "muted", True)
        outer.addWidget(self.run_summary)
        metric_row = QHBoxLayout()
        for key, title, unit in [("flow_ml_min", "Flow", "mL/min"), ("pressure_psi", "Pressure", "psi"), ("flux_lmh", "Flux", "L/m²/h"), ("mass_g", "Balance mass", "g")]:
            frame = QFrame()
            frame.setObjectName("metricCard")
            card = QVBoxLayout(frame)
            card.setContentsMargins(13, 9, 13, 9)
            card.setSpacing(0)
            card.addWidget(_label(title, "muted"))
            value = _label("Waiting", "metricValue")
            value.setAccessibleName(f"Current {title.lower()}")
            card.addWidget(value)
            card.addWidget(_label(unit, "metricUnit"))
            self._metric_labels[key] = value
            metric_row.addWidget(frame)
        outer.addLayout(metric_row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        charts = QWidget()
        grid = QGridLayout(charts)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        definitions = [("flow_ml_min", "Flow", "mL/min", "#258b91"), ("pressure_psi", "Pressure", "psi", "#497eae"), ("flux_lmh", "Flux", "L/m²/h", "#8667aa"), ("mass_g", "Balance mass", "g", "#bb8250")]
        for index, (key, title, unit, color) in enumerate(definitions):
            plot = pg.PlotWidget()
            plot.setMinimumHeight(135)
            plot.setTitle(title, color="#385366", size="10pt")
            plot.setLabel("left", unit)
            plot.setLabel("bottom", "Time", units="s")
            plot.showGrid(x=True, y=True, alpha=0.12)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=True, y=True)
            plot.getAxis("left").setWidth(58)
            plot.getAxis("left").enableAutoSIPrefix(False)
            plot.getAxis("bottom").enableAutoSIPrefix(False)
            plot.getViewBox().setLimits(xMin=0, minXRange=5,
                                       minYRange=0.5 if key == "pressure_psi" else 1)
            self._curves[key] = plot.plot(pen=pg.mkPen(color, width=2))
            grid.addWidget(plot, index // 2, index % 2)
        splitter.addWidget(charts)

        lower = QWidget()
        low_layout = QHBoxLayout(lower)
        low_layout.setContentsMargins(0, 0, 0, 0)
        manual = QGroupBox("Manual output commands")
        manual_layout = QVBoxLayout(manual)
        manual_layout.addWidget(_label("Commanded states only. Valve position feedback is not available.", "muted", True))
        valve_row = QHBoxLayout()
        self.valve_buttons: list[QToolButton] = []
        for index in range(7):
            button = QToolButton()
            button.setText(f"V{index + 1}\nOFF")
            button.setCheckable(True)
            button.setAccessibleName(f"Valve {index + 1} commanded state")
            button.setToolTip(f"Command valve {index + 1}; this does not confirm physical position")
            button.clicked.connect(self._manual_command)
            self.valve_buttons.append(button)
            valve_row.addWidget(button)
        manual_layout.addLayout(valve_row)
        pump_row = QHBoxLayout()
        pump_row.addWidget(_label("Pump command"))
        self.manual_pump = QDoubleSpinBox()
        self.manual_pump.setRange(0, 100)
        self.manual_pump.setDecimals(1)
        self.manual_pump.setSuffix(" %")
        self.manual_pump.setAccessibleName("Manual pump command percent")
        pump_row.addWidget(self.manual_pump)
        self.manual_apply = _button("Apply pump", self._manual_command)
        pump_row.addWidget(self.manual_apply)
        pump_row.addStretch()
        manual_layout.addLayout(pump_row)
        low_layout.addWidget(manual, 3)
        log_group = QGroupBox("Activity")
        log_layout = QVBoxLayout(log_group)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setPlaceholderText("Connection changes, run events and faults appear here.")
        self.activity.setMaximumBlockCount(100)
        self.activity.setAccessibleName("Activity log")
        log_layout.addWidget(self.activity)
        low_layout.addWidget(log_group, 2)
        splitter.addWidget(lower)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)
        trace_row = QHBoxLayout()
        trace_row.addWidget(_label("Live traces retain the latest 600 points. CSV recording is configured separately.", "muted"))
        trace_row.addStretch()
        trace_row.addWidget(_button("Clear traces", self._clear_traces))
        outer.addLayout(trace_row)
        self.tabs.addTab(page, "Dashboard")

    def _build_editor(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(17, 15, 17, 15)
        layout.addWidget(_label("Demo templates are examples, not verified versions of the original lab routines. Check the sequence against the actual system.", "muted", True))
        form = QGridLayout()
        self.recipe_name = QLineEdit()
        self.recipe_name.setAccessibleName("Recipe name")
        self.recipe_description = QLineEdit()
        self.recipe_description.setAccessibleName("Recipe description")
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 100)
        self.repeat_spin.valueChanged.connect(self._update_editor_duration)
        self.repeat_spin.setAccessibleName("Sequence repeat count")
        self.sample_spin = QDoubleSpinBox()
        self.sample_spin.setRange(0.1, 3600)
        self.sample_spin.setDecimals(2)
        self.sample_spin.setSuffix(" s")
        self.sample_spin.setValue(30)
        self.sample_spin.setAccessibleName("Recipe recording interval seconds")
        self.recipe_balance = QCheckBox("Require balance data")
        self.recipe_approved = QCheckBox("Recipe verified for this hardware")
        self.recipe_approved.setToolTip("Record this only after checking every output and transition against the installed system")
        form.addWidget(_label("Name"), 0, 0)
        form.addWidget(self.recipe_name, 0, 1, 1, 3)
        form.addWidget(_label("Description"), 1, 0)
        form.addWidget(self.recipe_description, 1, 1, 1, 3)
        form.addWidget(_label("Repeats"), 2, 0)
        form.addWidget(self.repeat_spin, 2, 1)
        form.addWidget(_label("Record every"), 2, 2)
        form.addWidget(self.sample_spin, 2, 3)
        form.addWidget(self.recipe_balance, 3, 1)
        form.addWidget(self.recipe_approved, 3, 3)
        form.setColumnStretch(1, 2)
        form.setColumnStretch(3, 2)
        layout.addLayout(form)

        self.steps_table = QTableWidget(0, 10)
        self.steps_table.setAccessibleName("Editable experiment sequence steps")
        self.steps_table.setHorizontalHeaderLabels(["Step name", "Duration s"] + [f"V{i}" for i in range(1, 8)] + ["Pump %"])
        self.steps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.steps_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.steps_table.setAlternatingRowColors(True)
        self.steps_table.verticalHeader().setDefaultSectionSize(41)
        header = self.steps_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 10):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.steps_table.setColumnWidth(col, 62 if 2 <= col <= 8 else 105)
        layout.addWidget(self.steps_table, 1)
        row = QHBoxLayout()
        self._editor_edit_buttons = []
        for text, callback in [("Add step", self._add_step), ("Remove step", self._remove_step), ("Move up", lambda: self._move_step(-1)), ("Move down", lambda: self._move_step(1))]:
            button = _button(text, callback)
            self._editor_edit_buttons.append(button)
            row.addWidget(button)
        row.addStretch()
        self.editor_duration = _label("", "muted")
        row.addWidget(self.editor_duration)
        layout.addLayout(row)
        bottom = QHBoxLayout()
        self.apply_recipe_button = _button("Apply sequence", self._apply_recipe, "primaryButton")
        bottom.addWidget(self.apply_recipe_button)
        self.save_as_button = _button("Save as", self._save_as_recipe)
        self.import_button = _button("Import JSON", self._import_recipe)
        bottom.addWidget(self.save_as_button)
        bottom.addWidget(self.import_button)
        bottom.addWidget(_button("Export JSON", self._export_recipe))
        bottom.addStretch()
        layout.addLayout(bottom)
        self.tabs.addTab(page, "Sequence editor")

    def _build_connections(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.addWidget(_label("Connect devices explicitly. Detecting a USB adapter alone does not establish a responding controller.", "muted", True))
        devices = QHBoxLayout()
        controller_box = QGroupBox("ESP32 controller")
        cform = QFormLayout(controller_box)
        self.controller_port = QComboBox()
        self.controller_port.setAccessibleName("Controller serial port")
        cform.addRow("Serial port", self.controller_port)
        crow = QHBoxLayout()
        self.controller_connect = _button("Connect", self._connect_controller)
        self.controller_disconnect = _button("Disconnect", lambda: self._action(self.controller.disconnect_controller, "Controller disconnected"))
        crow.addWidget(self.controller_connect)
        crow.addWidget(self.controller_disconnect)
        cform.addRow(crow)
        self.controller_detail = _label("No controller connected", "muted", True)
        cform.addRow(self.controller_detail)
        devices.addWidget(controller_box)
        balance_box = QGroupBox("Balance")
        bform = QFormLayout(balance_box)
        self.balance_port = QComboBox()
        self.balance_port.setAccessibleName("Balance serial port")
        self.balance_baud = QComboBox()
        self.balance_baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.balance_baud.setAccessibleName("Balance serial baud rate")
        bform.addRow("Serial port", self.balance_port)
        bform.addRow("Baud rate", self.balance_baud)
        brow = QHBoxLayout()
        self.balance_connect = _button("Connect", self._connect_balance)
        self.balance_disconnect = _button("Disconnect", lambda: self._action(self.controller.disconnect_balance, "Balance disconnected"))
        brow.addWidget(self.balance_connect)
        brow.addWidget(self.balance_disconnect)
        bform.addRow(brow)
        self.balance_detail = _label("No balance connected", "muted", True)
        bform.addRow(self.balance_detail)
        devices.addWidget(balance_box)
        layout.addLayout(devices)
        refresh = QHBoxLayout()
        refresh.addWidget(_button("Refresh serial ports", self._refresh_ports))
        refresh.addStretch()
        layout.addLayout(refresh)

        settings_box = QGroupBox("Measurement and recording settings")
        settings = QFormLayout(settings_box)
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setDecimals(6)
        self.area_spin.setRange(0.000001, 1000)
        self.area_spin.setSuffix(" m²")
        self.area_spin.setAccessibleName("Membrane area square metres")
        self.density_spin = QDoubleSpinBox()
        self.density_spin.setDecimals(4)
        self.density_spin.setRange(0.0001, 100)
        self.density_spin.setSuffix(" g/mL")
        self.density_spin.setAccessibleName("Liquid density grams per millilitre")
        self.require_balance = QCheckBox("Require balance for every run")
        self.pressure_limit_spin = QDoubleSpinBox()
        self.pressure_limit_spin.setRange(0.1, 100)
        self.pressure_limit_spin.setDecimals(1)
        self.pressure_limit_spin.setSuffix(" psi")
        self.pressure_limit_spin.setAccessibleName("Desktop pressure stop threshold psi")
        self.hardware_status = _label("Interface verification is reported by the controller firmware.", "muted", True)
        settings.addRow("Membrane area", self.area_spin)
        settings.addRow("Liquid density", self.density_spin)
        settings.addRow("Desktop pressure stop threshold", self.pressure_limit_spin)
        settings.addRow(self.require_balance)
        settings.addRow(self.hardware_status)
        settings.addRow(_label("Flux uses the configured membrane area. Balance flow uses changes in mass and the configured liquid density.", "muted", True))
        self.settings_apply = _button("Save settings", self._save_settings, "primaryButton")
        settings.addRow(self.settings_apply)
        layout.addWidget(settings_box)
        layout.addStretch()
        self.tabs.addTab(page, "Connections and settings")

    def _build_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(17, 15, 17, 15)
        layout.addWidget(_label("Recorded runs stay local. Select a run to export its measurements as CSV.", "muted", True))
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(["Started UTC", "Recipe", "Status", "Ended UTC", "Run ID"])
        self.history_table.setAccessibleName("Recorded run history")
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.history_table, 1)
        self.history_empty = _label("No runs recorded yet. Start a simulation to explore the full recording workflow.", "muted", True)
        layout.addWidget(self.history_empty)
        row = QHBoxLayout()
        row.addWidget(_button("Refresh history", self._refresh_history))
        self.history_export = _button("Export selected run", self._export_history)
        row.addWidget(self.history_export)
        row.addStretch()
        layout.addLayout(row)
        self.tabs.addTab(page, "Run history")
        self.tabs.currentChanged.connect(lambda index: self._refresh_history() if index == 3 else None)

    def _action(self, callback, success: str = "", show_dialog: bool = True):
        try:
            result = callback()
            if success:
                self.statusBar().showMessage(success, 6000)
            return result
        except Exception as exc:
            self.statusBar().showMessage(str(exc), 12000)
            if show_dialog:
                QMessageBox.warning(self, "Action could not be completed", str(exc))
            return None

    def _load_presets(self):
        try:
            self._presets = self.controller.list_presets()
            with QSignalBlocker(self.preset_combo):
                previous = self.preset_combo.currentData()
                self.preset_combo.clear()
                for name in self._presets:
                    label = name[:-5] + "  |  demo template" if name.lower().endswith(" demo") else name + "  |  custom"
                    self.preset_combo.addItem(label, name)
                old_index = self.preset_combo.findData(previous)
                if old_index >= 0:
                    self.preset_combo.setCurrentIndex(old_index)
        except Exception as exc:
            self.statusBar().showMessage(f"Presets unavailable: {exc}")

    def _select_preset(self, index: int):
        if self._updating or index < 0:
            return
        name = self.preset_combo.itemData(index)
        recipe = self._presets.get(name)
        if recipe is None:
            return
        try:
            self.controller.load_recipe(recipe)
            self._populate_recipe(recipe)
            self.statusBar().showMessage(f"Loaded sequence: {recipe.name}", 5000)
        except Exception as exc:
            self.statusBar().showMessage(str(exc), 10000)

    def _populate_recipe(self, recipe: Recipe):
        self._editor_recipe = recipe
        self.recipe_name.setText(recipe.name)
        self.recipe_description.setText(recipe.description)
        self.repeat_spin.setValue(recipe.repeat)
        self.sample_spin.setValue(recipe.sample_interval_s)
        self.recipe_balance.setChecked(recipe.require_balance)
        self.recipe_approved.setChecked(recipe.hardware_approved)
        self._populate_steps([{"name": s.name, "duration_s": s.duration_s, "valves": list(s.valves), "pump_percent": s.pump_percent} for s in recipe.steps])

    def _populate_steps(self, steps: list[dict]):
        self.steps_table.setRowCount(0)
        for row, step in enumerate(steps):
            self.steps_table.insertRow(row)
            self.steps_table.setItem(row, 0, QTableWidgetItem(str(step["name"])))
            duration = QDoubleSpinBox()
            duration.setRange(0.1, 86400)
            duration.setDecimals(1)
            duration.setValue(float(step["duration_s"]))
            duration.setAccessibleName(f"Step {row + 1} duration seconds")
            duration.valueChanged.connect(self._update_editor_duration)
            self.steps_table.setCellWidget(row, 1, duration)
            for valve in range(7):
                holder = QWidget()
                cell_layout = QHBoxLayout(holder)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                check = QCheckBox()
                check.setChecked(bool(step["valves"][valve]))
                check.setAccessibleName(f"Step {row + 1} valve {valve + 1} commanded on")
                cell_layout.addWidget(check)
                self.steps_table.setCellWidget(row, valve + 2, holder)
            pump = QDoubleSpinBox()
            pump.setRange(0, 100)
            pump.setDecimals(1)
            pump.setValue(float(step["pump_percent"]))
            pump.setAccessibleName(f"Step {row + 1} pump percent")
            self.steps_table.setCellWidget(row, 9, pump)
        self._update_editor_duration()

    def _step_data(self) -> list[dict]:
        rows = []
        for row in range(self.steps_table.rowCount()):
            name_item = self.steps_table.item(row, 0)
            rows.append({
                "name": name_item.text().strip() if name_item else "",
                "duration_s": self.steps_table.cellWidget(row, 1).value(),
                "valves": [self.steps_table.cellWidget(row, col).findChild(QCheckBox).isChecked() for col in range(2, 9)],
                "pump_percent": self.steps_table.cellWidget(row, 9).value(),
            })
        return rows

    def _collect_recipe(self) -> Recipe:
        recipe = Recipe.from_dict({
            "schema_version": 1,
            "name": self.recipe_name.text().strip(),
            "description": self.recipe_description.text().strip(),
            "hardware_approved": self.recipe_approved.isChecked(),
            "repeat": self.repeat_spin.value(),
            "sample_interval_s": self.sample_spin.value(),
            "require_balance": self.recipe_balance.isChecked(),
            "steps": self._step_data(),
        })
        errors = recipe.validate()
        if isinstance(errors, (list, tuple)) and errors:
            raise ValueError("\n".join(map(str, errors)))
        return recipe

    def _apply_recipe(self):
        def apply():
            recipe = self._collect_recipe()
            self.controller.load_recipe(recipe)
            self._editor_recipe = recipe
        self._action(apply, "Sequence applied. Ready to start when required devices are available.")

    def _add_step(self):
        steps = self._step_data()
        steps.append({"name": f"Step {len(steps) + 1}", "duration_s": 60, "valves": [False] * 7, "pump_percent": 0})
        self._populate_steps(steps)
        self.steps_table.selectRow(len(steps) - 1)

    def _remove_step(self):
        row = self.steps_table.currentRow()
        if row >= 0:
            self.steps_table.removeRow(row)
            self._update_editor_duration()

    def _move_step(self, offset: int):
        row = self.steps_table.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.steps_table.rowCount():
            return
        steps = self._step_data()
        steps[row], steps[target] = steps[target], steps[row]
        self._populate_steps(steps)
        self.steps_table.selectRow(target)

    def _update_editor_duration(self, *_):
        try:
            total = sum(s["duration_s"] for s in self._step_data()) * self.repeat_spin.value()
            self.editor_duration.setText(f"Total duration: {total:,.1f} s")
        except (AttributeError, RuntimeError):
            pass

    def _save_as_recipe(self):
        name, accepted = QInputDialog.getText(self, "Save custom recipe", "Recipe name", text=self.recipe_name.text())
        if accepted and name.strip():
            self.recipe_name.setText(name.strip())
            self._export_recipe()

    def _export_recipe(self):
        try:
            recipe = self._collect_recipe()
        except Exception as exc:
            QMessageBox.warning(self, "Check the sequence", str(exc))
            return
        safe_name = "".join(c for c in recipe.name if c.isalnum() or c in " -_").strip() or "recipe"
        path, _ = QFileDialog.getSaveFileName(self, "Export recipe", f"{safe_name}.json", "Recipe JSON (*.json)")
        if path:
            if not path.lower().endswith(".json"):
                path += ".json"
            def save():
                self.controller.save_recipe(path, recipe)
                self._load_presets()
            self._action(save, f"Recipe saved to {path}")

    def _import_recipe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import recipe", "", "Recipe JSON (*.json)")
        if not path:
            return
        def load():
            recipe = self.controller.load_recipe_file(path)
            self.controller.load_recipe(recipe)
            self._populate_recipe(recipe)
        self._action(load, "Recipe imported and applied")

    def _start_run(self):
        def start():
            recipe = self._collect_recipe()
            self.controller.load_recipe(recipe)
            self._editor_recipe = recipe
            self.controller.start_run()
        self._action(start, "Run started")

    def _stop_run(self):
        self._action(self.controller.stop_run, "Stop requested")
        self._refresh_history()

    def _clear_fault(self):
        def clear():
            self.controller.clear_fault()
            self._timer_fault = ""
            self._timer_stop_requested = False
        self._action(clear, "Fault clear requested. Outputs remain stopped.")

    def _manual_command(self, *_):
        if self._updating:
            return
        self._action(lambda: self.controller.set_manual([b.isChecked() for b in self.valve_buttons], self.manual_pump.value()), "Manual output command sent")

    def _toggle_simulation(self, enabled: bool):
        if not hasattr(self, "banner"):
            return
        self._action(lambda: self.controller.set_simulation(enabled), "Simulation mode enabled" if enabled else "Hardware mode selected")

    def _refresh_ports(self):
        try:
            ports = self.controller.list_ports()
            for combo in (self.controller_port, self.balance_port):
                previous = combo.currentData()
                combo.clear()
                for device, description in ports:
                    combo.addItem(f"{device}  {description}", device)
                if combo.count() == 0:
                    combo.addItem("No serial ports found", None)
                index = combo.findData(previous)
                if index >= 0:
                    combo.setCurrentIndex(index)
        except Exception as exc:
            self.statusBar().showMessage(f"Could not list serial ports: {exc}", 10000)

    def _connect_controller(self):
        port = self.controller_port.currentData()
        if port:
            self._action(lambda: self.controller.connect_controller(port), "Controller connection requested")
        else:
            self.statusBar().showMessage("Select a controller serial port first", 6000)

    def _connect_balance(self):
        port = self.balance_port.currentData()
        if port:
            self._action(lambda: self.controller.connect_balance(port, int(self.balance_baud.currentText())), "Balance connection requested")
        else:
            self.statusBar().showMessage("Select a balance serial port first", 6000)

    def _load_settings(self):
        settings = self.controller.settings
        self.area_spin.setValue(float(settings.get("membrane_area_m2", 0.1)))
        self.density_spin.setValue(float(settings.get("density_g_ml", 1)))
        self.require_balance.setChecked(bool(settings.get("require_balance", True)))
        self.pressure_limit_spin.setValue(float(settings.get("max_pressure_psi", 20)))

    def _save_settings(self):
        values = {
            "membrane_area_m2": self.area_spin.value(),
            "density_g_ml": self.density_spin.value(),
            "require_balance": self.require_balance.isChecked(),
            "max_pressure_psi": self.pressure_limit_spin.value(),
        }
        self._action(lambda: self.controller.update_settings(values), "Settings saved")

    def _refresh_history(self):
        try:
            self._history = self.controller.list_runs()
            self.history_table.setRowCount(len(self._history))
            for row, run in enumerate(self._history):
                values = [run.get("started_at", run.get("started_utc", "")), run.get("recipe_name", run.get("name", run.get("recipe", ""))), run.get("status", run.get("state", "")), run.get("ended_utc") or "In progress", run.get("run_id", run.get("id", ""))]
                for column, value in enumerate(values):
                    self.history_table.setItem(row, column, QTableWidgetItem(str(value)))
            self.history_empty.setVisible(not self._history)
            self.history_export.setEnabled(bool(self._history))
        except Exception as exc:
            self.history_empty.setText(f"Run history unavailable: {exc}")
            self.history_empty.show()

    def _export_current(self):
        self._export_csv(None)

    def _export_history(self):
        row = self.history_table.currentRow()
        if not 0 <= row < len(self._history):
            self.statusBar().showMessage("Select a recorded run to export", 6000)
            return
        run = self._history[row]
        self._export_csv(run.get("run_id", run.get("id")))

    def _export_csv(self, run_id):
        path, _ = QFileDialog.getSaveFileName(self, "Export measurements", "membrane-run.csv", "CSV files (*.csv)")
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            self._action(lambda: self.controller.export_csv(path, run_id=run_id), f"CSV exported to {path}")

    def _clear_traces(self):
        self._plot_time.clear()
        for values in self._plot_data.values():
            values.clear()
        for curve in self._curves.values():
            curve.setData([], [])
        self._plot_start = time.monotonic()

    def _on_tick(self):
        try:
            self.controller.tick()
            self._update_view(dict(self.controller.snapshot))
        except Exception as exc:
            now = time.monotonic()
            message = f"Update failed: {exc}"
            self._timer_fault = message
            if not self._timer_stop_requested:
                self._timer_stop_requested = True
                try:
                    self.controller.stop_run()
                except Exception as stop_error:
                    message += f". Stop request failed: {stop_error}"
                    try:
                        self.controller.disconnect_controller()
                    except Exception:
                        pass
                log = getattr(self.controller, "log", None)
                if log is not None and hasattr(log, "append"):
                    log.append(message)
                self.fault_label.setText(message + ". A stop was requested. Clear the fault after checking the system.")
                self.fault_label.show()
                self.clear_fault_button.show()
                self.start_button.setEnabled(False)
            if message != self._last_error or now - self._last_error_at > 5:
                self.statusBar().showMessage(message, 10000)
                self._last_error, self._last_error_at = message, now

    def _update_view(self, snap: dict):
        self._updating = True
        try:
            state = str(snap.get("state", "idle"))
            simulation = bool(snap.get("simulation", True))
            desktop_simulation = bool(getattr(self.controller, "simulation", simulation))
            active = state.upper() in {"RUNNING", "PAUSED", "STOPPING"} or bool(snap.get("start_pending")) or bool(snap.get("stop_pending"))
            operating = active or state.upper() == "MANUAL"
            fault = str(snap.get("fault") or self._timer_fault or "")
            connected = bool(snap.get("controller_connected", False))
            balanced = bool(snap.get("balance_connected", False))
            verified = bool(snap.get("hardware_verified", False))
            needs_balance = self.recipe_balance.isChecked() or bool(self.controller.settings.get("require_balance", False))
            last_telemetry = getattr(self.controller, "last_telemetry", None)
            fresh = last_telemetry is not None and self.controller.clock() - last_telemetry <= 2 if hasattr(self.controller, "clock") else connected
            ready = connected and fresh and (simulation or (verified and self.recipe_approved.isChecked() and snap.get("pressure_psi") is not None)) and (balanced or not needs_balance)
            self.state_chip.setText("STOPPING" if snap.get("stop_pending") else ("STARTING" if snap.get("start_pending") else state.replace("_", " ").upper()))
            with QSignalBlocker(self.simulation_check):
                self.simulation_check.setChecked(desktop_simulation)
            self.simulation_check.setEnabled(not operating)
            self.banner.setObjectName("simulationBanner" if simulation else "hardwareBanner")
            self.banner.setStyleSheet("color: #79520a; background: #fff5dc; border: 1px solid #ead398; border-radius: 6px; padding: 10px;" if simulation else "color: #215265; background: #eaf3f7; border: 1px solid #cbdfe8; border-radius: 6px; padding: 10px;")
            self.banner.setText("SIMULATION  •  Generated measurements and virtual outputs. No connected hardware is controlled." if desktop_simulation else ("DRY RUN FIRMWARE  •  The connected controller reports simulated measurements and outputs." if simulation and connected else ("HARDWARE MODE  •  Device readings are live. Verify the selected recipe and installation before starting." if verified else "HARDWARE MODE  •  Firmware reports an unverified installation. Hardware output commands are locked.")))
            self.fault_label.setVisible(bool(fault))
            self.fault_label.setText(f"Run stopped or blocked: {fault}" if fault else "")
            self.start_button.setEnabled(not operating and ready and not fault and self.steps_table.rowCount() > 0)
            self.start_button.setToolTip("Start the edited sequence" if ready else "Connect required devices and verify the hardware installation")
            self.stop_button.setEnabled(connected or operating or bool(fault))
            self.clear_fault_button.setVisible(bool(fault))
            self.clear_fault_button.setEnabled(bool(fault) and connected)
            for widget in (self.preset_combo, self.apply_recipe_button, self.steps_table, self.recipe_approved,
                           self.settings_apply, self.recipe_name, self.recipe_description, self.repeat_spin,
                           self.sample_spin, self.recipe_balance, self.import_button, self.save_as_button,
                           *self._editor_edit_buttons):
                widget.setEnabled(not operating)
            manual = not active and ready and not fault
            for index, button in enumerate(self.valve_buttons):
                actual = list(snap.get("valves") or [False] * 7)
                commanded = bool(actual[index]) if index < len(actual) else False
                with QSignalBlocker(button):
                    button.setChecked(commanded)
                button.setText(f"V{index + 1}\n{'ON' if commanded else 'OFF'}")
                button.setEnabled(manual)
            self.manual_pump.setEnabled(manual)
            self.manual_apply.setEnabled(manual)
            if active or state.upper() == "FAULT" or (self._previous_state != state and state.upper() == "IDLE"):
                self.manual_pump.setValue(float(snap.get("pump_percent") or 0))
            for key, label in self._metric_labels.items():
                label.setText(_number(snap.get(key), 1 if key in {"flow_ml_min", "flux_lmh"} else 2))
            self.controller_badge.setText(f"Controller: {'simulated' if desktop_simulation else ('connected' if connected else 'disconnected')}")
            self.balance_badge.setText(f"Balance: {'simulated' if desktop_simulation else ('connected' if balanced else 'disconnected')}")
            self.controller_detail.setText(str(snap.get("controller_status") or "No responding controller"))
            self.balance_detail.setText(str(snap.get("balance_status") or "No valid balance data"))
            self.hardware_status.setText("Controller interface verification: " + ("simulated" if simulation else ("verified by firmware" if verified else "not verified by firmware")))
            self.controller_connect.setEnabled(not operating and not desktop_simulation)
            self.balance_connect.setEnabled(not operating and not desktop_simulation)
            self.controller_disconnect.setEnabled(not operating and connected and not desktop_simulation)
            self.balance_disconnect.setEnabled(not operating and balanced and not desktop_simulation)
            self.export_current_button.setEnabled(bool(snap.get("run_id")))
            recipe_name = snap.get("recipe_name") or self.recipe_name.text() or "No sequence"
            if active:
                self.run_summary.setText(f"{recipe_name}  |  Cycle {snap.get('cycle', 1)}  |  {snap.get('step_name') or 'Step ' + str(int(snap.get('step_index', 0)) + 1)}  |  {_number(snap.get('remaining_s'), 1)} s remaining  |  {_number(snap.get('elapsed_s'), 1)} s elapsed")
            else:
                self.run_summary.setText(f"{recipe_name}  |  {state.replace('_', ' ').capitalize()}  |  Commanded pump {_number(snap.get('pump_percent', 0), 1)} %")
            logs = "\n".join(str(line) for line in snap.get("log", [])[-100:])
            if logs != self._last_log:
                self.activity.setPlainText(logs)
                self.activity.verticalScrollBar().setValue(self.activity.verticalScrollBar().maximum())
                self._last_log = logs
            now = time.monotonic()
            if now - self._last_plot >= 0.25:
                self._last_plot = now
                self._plot_time.append(now - self._plot_start)
                for key, points in self._plot_data.items():
                    try:
                        value = float(snap.get(key))
                    except (TypeError, ValueError):
                        value = float("nan")
                    points.append(value)
                    self._curves[key].setData(list(self._plot_time), list(points), connect="finite")
            self._previous_state = state
        finally:
            self._updating = False

    def closeEvent(self, event):
        self.timer.stop()
        try:
            self.controller.close()
        except Exception:
            pass
        event.accept()
