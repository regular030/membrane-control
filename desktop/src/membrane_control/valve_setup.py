"""Prepare a private valve-only build from an operator's recorded relay map."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from PySide6.QtCore import Qt, QSaveFile, QIODevice
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from .valve_profile import validate_profile


REVIEW_LABELS = (
    ('mapping_verified', 'Each bit below was individually measured with relay contact loads disconnected'),
    ('rest_word_verified', 'The full all-off pattern was checked, including unused relay outputs'),
    ('reset_oe_safe_verified', 'Reset, output-disable and power loss safely release the solenoids'),
    ('solenoid_loads_verified', 'A qualified person checked the single-coil solenoid circuits and mains installation'),
    ('pump_excluded_verified', 'The pump power and remote connections are physically isolated'),
    ('reviewed', 'The completed valve-only setup and test fluid paths have been reviewed'),
)


def find_setup_root() -> Path:
    """Only use a complete source checkout or the app's installed tool tree."""
    candidates = [Path(sys.executable).parent] if getattr(sys, 'frozen', False) else [Path(__file__).resolve().parents[3]]
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'MembraneControl')
    for root in candidates:
        if (root / 'packaging/prepare_valve_test.ps1').is_file() and (root / 'firmware/platformio.ini').is_file():
            return root.resolve()
    raise ValueError('Install the latest Membrane Control Setup EXE first. The app-only EXE does not include the build tools.')


def flash_command(root: Path, profile: Path, workspace: Path, port: str) -> list[str]:
    port = port.strip().upper()
    if not re.fullmatch(r'COM[1-9][0-9]{0,3}', port):
        raise ValueError('Choose the ESP32 COM port, such as COM4, before preparing the upload.')
    return ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(root / 'packaging/prepare_valve_test.ps1'), '-InstallRoot', str(root),
            '-Profile', str(profile), '-Workspace', str(workspace), '-Port', port]


class ValveSetupDialog(QDialog):
    """No port access: the explicit flash action opens a separate, interactive helper."""

    def __init__(self, parent=None, *, port='', directory=None, launcher=None):
        super().__init__(parent)
        self.port = port
        self.directory = Path(directory) if directory else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MembraneControl' / 'valve-setup'
        self.launcher = launcher or self._launch
        self.prepared_profile_id = None
        self.setWindowTitle('Set up valves without sensors')
        self.resize(700, 720)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        notice = QLabel('No pressure, flow or balance connection is needed. This prepares a separate '
                        'valve-only program. It cannot run the pump or an experiment. First record '
                        'the individual relay bits using the bare relay test with contact loads disconnected.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.profile_id = QLineEdit('valves-' + uuid.uuid4().hex[:10])
        self.profile_id.setMaxLength(64)
        self.profile_id.setAccessibleName('Unique valve setup ID')
        form.addRow('Setup ID', self.profile_id)
        self.bit_combos = []
        for index in range(7):
            combo = QComboBox()
            combo.addItem('Choose the measured raw bit', None)
            for bit in range(16):
                combo.addItem(f'Bit {bit}', bit)
            combo.setAccessibleName(f'Valve {index + 1} measured relay bit')
            self.bit_combos.append(combo)
            form.addRow(f'V{index + 1}', combo)
        self.rest_combo = QComboBox()
        self.rest_combo.addItem('Choose the measured all-off pattern', None)
        self.rest_combo.addItem('All LOW (0): every relay off', 0)
        self.rest_combo.addItem('All HIGH (65535): every relay off', 65535)
        self.rest_combo.addItem('Other measured 16-bit pattern', 'custom')
        form.addRow('All-off pattern', self.rest_combo)
        self.custom_rest = QSpinBox()
        self.custom_rest.setRange(0, 65535)
        self.custom_rest.setEnabled(False)
        form.addRow('Other pattern (decimal)', self.custom_rest)
        layout.addLayout(form)
        explanation = QLabel('All LOW off / All HIGH on identifies polarity. It does not identify '
                             'which bit operates V1, V2 and so on. Leave unknown mappings blank. '
                             'These are raw bit numbers, not ESP32 GPIO numbers.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.reviews = {}
        for key, text in REVIEW_LABELS:
            box = QCheckBox(text)
            box.setAccessibleName(text)
            self.reviews[key] = box
            layout.addWidget(box)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.save_button = QPushButton('Save draft')
        self.save_button.clicked.connect(self.save_draft)
        self.flash_button = QPushButton('Build and flash valve setup')
        self.flash_button.clicked.connect(self.prepare_flash)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        for button in (self.save_button, self.flash_button, self.close_button):
            row.addWidget(button)
        outer.addLayout(row)
        self._load_draft()
        for widget in [self.profile_id, *self.bit_combos, self.rest_combo, self.custom_rest]:
            signal = widget.textChanged if isinstance(widget, QLineEdit) else widget.currentIndexChanged if isinstance(widget, QComboBox) else widget.valueChanged
            signal.connect(self._mapping_changed)
        for box in self.reviews.values():
            box.toggled.connect(self._render)
        self._render()

    def data(self):
        rest = self.rest_combo.currentData()
        return {'profile_id': self.profile_id.text().strip(),
                'valve_bits': [combo.currentData() for combo in self.bit_combos],
                'rest_word': self.custom_rest.value() if rest == 'custom' else rest,
                **{key: box.isChecked() for key, box in self.reviews.items()}}

    def _mapping_changed(self, *_):
        # A changed mapping needs its own review, never inherit old approvals.
        for box in self.reviews.values():
            box.setChecked(False)
        self._render()

    def _render(self, *_):
        self.custom_rest.setEnabled(self.rest_combo.currentData() == 'custom')
        try:
            validate_profile(self.data(), require_reviewed=True)
            if not re.fullmatch(r'COM[1-9][0-9]{0,3}', self.port.strip().upper()):
                raise ValueError('Select the ESP32 COM port in the valve-test window first.')
        except (ValueError, TypeError) as error:
            self.flash_button.setEnabled(False)
            self.message.setText(str(error))
        else:
            self.flash_button.setEnabled(True)
            self.message.setText('Ready to prepare a private valve-only build. The helper asks again before upload. '
                                 'Disconnect relay contact loads for the initial upload; reconnect only after the installation checks.')

    def _write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        target = QSaveFile(str(path))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        encoded = (json.dumps(data, indent=2) + '\n').encode('utf-8')
        if target.write(encoded) != len(encoded) or not target.commit():
            raise OSError(target.errorString())

    def save_draft(self):
        try:
            self._write(self.directory / 'valve-profile-draft.json', self.data())
            self.message.setText('Draft saved locally. Reviews must be repeated when you reopen it; no hardware was accessed.')
        except OSError as error:
            QMessageBox.warning(self, 'Could not save draft', str(error))

    def _load_draft(self):
        path = self.directory / 'valve-profile-draft.json'
        try:
            if path.stat().st_size > 32768:
                return
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return
            if isinstance(data.get('profile_id'), str):
                # Every reopened build gets a fresh ID, even if its mapping is reused.
                self.profile_id.setText('valves-' + uuid.uuid4().hex[:10])
            bits = data.get('valve_bits')
            if isinstance(bits, list) and len(bits) == 7:
                for combo, bit in zip(self.bit_combos, bits):
                    if type(bit) is int and 0 <= bit <= 15:
                        combo.setCurrentIndex(combo.findData(bit))
            rest = data.get('rest_word')
            if type(rest) is int and 0 <= rest <= 65535:
                index = self.rest_combo.findData(rest)
                self.rest_combo.setCurrentIndex(index if index >= 0 else self.rest_combo.findData('custom'))
                self.custom_rest.setValue(rest)
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _launch(command):
        subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def prepare_flash(self):
        try:
            data = self.data()
            validate_profile(data, require_reviewed=True)
            root = find_setup_root()
            token = uuid.uuid4().hex
            profile_path = self.directory / 'profiles' / f'{token}.json'
            workspace = self.directory / 'builds' / token
            command = flash_command(root, profile_path, workspace, self.port)
            self._write(profile_path, data)
            self._write(self.directory / 'valve-profile-draft.json', data)
            workspace.parent.mkdir(parents=True, exist_ok=True)
            self.launcher(command)
            self.prepared_profile_id = data['profile_id']
            self.accept()
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, 'Valve setup not started', str(error))
