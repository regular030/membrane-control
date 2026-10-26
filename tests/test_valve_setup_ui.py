"""Guided setup uses fake launchers and files only, never real serial ports."""
import json
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from membrane_control.valve_setup import ValveSetupDialog, flash_command
from membrane_control.valve_test import ValveTestSession, ValveTestDialog
from test_valve_test import FakeTransport, identity, connect_verified


@pytest.fixture(scope='module')
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qt_app, tmp_path):
    launched = []
    widget = ValveSetupDialog(port='COM4', directory=tmp_path / 'private data', launcher=launched.append)
    yield widget, launched
    widget.close()


def complete(widget):
    for bit, combo in enumerate(widget.bit_combos):
        combo.setCurrentIndex(combo.findData(bit))
    widget.rest_combo.setCurrentIndex(widget.rest_combo.findData(0))
    for box in widget.reviews.values():
        box.setChecked(True)


def test_blank_setup_never_invents_mapping_or_review(dialog):
    widget, launched = dialog
    assert widget.data()['valve_bits'] == [None] * 7
    assert widget.data()['rest_word'] is None
    assert not any(box.isChecked() for box in widget.reviews.values())
    assert not widget.flash_button.isEnabled()
    assert not launched
    assert not widget.directory.exists()


def test_distinct_mapping_reviews_and_real_port_required(dialog):
    widget, launched = dialog
    complete(widget)
    assert widget.flash_button.isEnabled()
    widget.bit_combos[6].setCurrentIndex(widget.bit_combos[0].currentIndex())
    assert not widget.flash_button.isEnabled()
    assert not any(box.isChecked() for box in widget.reviews.values())
    complete(widget)
    widget.port = 'COM4; run something'
    widget._render()
    assert not widget.flash_button.isEnabled() and not launched


def test_draft_preserves_unknown_fields_but_never_restores_reviews(dialog, qt_app):
    widget, launched = dialog
    widget.bit_combos[0].setCurrentIndex(widget.bit_combos[0].findData(9))
    widget.rest_combo.setCurrentIndex(widget.rest_combo.findData(0))
    widget.reviews['rest_word_verified'].setChecked(True)
    old_id = widget.profile_id.text()
    widget.save_draft()
    saved = json.loads((widget.directory / 'valve-profile-draft.json').read_text())
    assert saved['valve_bits'] == [9] + [None] * 6
    assert saved['rest_word'] == 0 and not launched
    reopened = ValveSetupDialog(port='COM4', directory=widget.directory, launcher=launched.append)
    try:
        assert reopened.data()['valve_bits'] == [9] + [None] * 6
        assert reopened.data()['rest_word'] == 0
        assert not any(box.isChecked() for box in reopened.reviews.values())
        assert reopened.profile_id.text() != old_id
        assert not reopened.flash_button.isEnabled()
    finally:
        reopened.close()


def test_explicit_prepare_writes_private_profile_and_launches_only_fixed_helper(dialog, monkeypatch):
    widget, launched = dialog
    complete(widget)
    root = widget.directory.parent / 'Installed tools with spaces'
    monkeypatch.setattr('membrane_control.valve_setup.find_setup_root', lambda: root)
    widget.prepare_flash()
    assert widget.prepared_profile_id == widget.profile_id.text()
    assert len(launched) == 1
    args = launched[0]
    assert args[:5] == ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    assert args[5] == str(root / 'packaging/prepare_valve_test.ps1')
    profile = Path(args[args.index('-Profile') + 1])
    workspace = Path(args[args.index('-Workspace') + 1])
    assert profile.is_relative_to(widget.directory)
    assert workspace.parent.is_dir() and not workspace.exists()
    saved = json.loads(profile.read_text())
    assert saved['valve_bits'] == list(range(7)) and saved['reviewed'] is True
    assert args[args.index('-Port') + 1] == 'COM4'


@pytest.mark.parametrize('port', ['', 'COM0', 'COM4 -t upload', 'COM4;exit', '../COM4'])
def test_upload_command_rejects_non_port_text(tmp_path, port):
    with pytest.raises(ValueError):
        flash_command(tmp_path, tmp_path / 'profile.json', tmp_path / 'build', port)


def test_expected_profile_mismatch_releases_connection_and_cannot_arm():
    transport = FakeTransport()
    session = ValveTestSession(lambda *_: transport)
    session.expected_profile_id = 'expected-rig-profile'
    session.connect('FAKE-ONLY')
    transport.events.append(identity(transport.last('hello')['id']))
    session.tick()
    assert transport.closed and session.transport is None
    assert 'expected-rig-profile' in session.error and not session.can_arm


def test_setup_entry_disabled_while_port_is_owned(qt_app):
    transport = FakeTransport()
    widget = ValveTestDialog(selected_port='FAKE-ONLY', port_lister=lambda: [],
                             transport_factory=lambda *_: transport)
    widget.timer.stop()
    try:
        assert widget.setup_button.isEnabled()
        connect_verified(widget.session, transport)
        widget._render()
        assert not widget.setup_button.isEnabled()
        # Guarded before constructing any setup dialog, even if invoked directly.
        widget._open_setup()
        assert widget.session.transport is transport
    finally:
        widget.close()


def test_expected_profile_persists_without_enabling_a_session(qt_app, tmp_path):
    tmp_path.joinpath('expected-profile.json').write_text(json.dumps({'profile_id': 'rig-confirmed-1'}))
    widget = ValveTestDialog(port_lister=lambda: [], setup_directory=tmp_path)
    widget.timer.stop()
    try:
        assert widget.session.expected_profile_id == 'rig-confirmed-1'
        assert widget.session.transport is None and not widget.session.can_arm
    finally:
        widget.close()
