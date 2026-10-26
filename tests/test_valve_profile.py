"""Profile preparation never uses hardware or changes the factory source tree."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from membrane_control.valve_profile import (
    GENERATED_FILES, PLATFORMIO_INI, REVIEW_FIELDS, SOURCE_FILES, checked_path,
    load_profile, prepare_workspace, profile_to_dict, render_profile_header,
    save_profile, validate_profile, workspace_plan,
)


def reviewed_profile(**changes):
    return {'profile_id': 'LAB-TEST-ONLY.1', 'valve_bits': [0, 2, 4, 6, 8, 10, 12],
            'rest_word': 32769, **dict.fromkeys(REVIEW_FIELDS, True), **changes}


@pytest.fixture
def source_tree(tmp_path):
    source = tmp_path / 'factory firmware'
    for name in SOURCE_FILES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'// untouched source: {name}\n', encoding='utf-8')
    (source / 'platformio.ini').write_text('FACTORY UNVERIFIED SETTINGS\n', encoding='utf-8')
    (source / 'do-not-copy.secret').write_text('unrelated private data', encoding='utf-8')
    return source


def tree_bytes(path):
    return {file.relative_to(path).as_posix(): file.read_bytes() for file in path.rglob('*') if file.is_file()}


def test_profile_roundtrip_preserves_measured_mapping_and_all_explicit_reviews(tmp_path):
    data = reviewed_profile()
    original = copy.deepcopy(data)
    profile = validate_profile(data, require_reviewed=True)
    assert profile.valve_bits == (0, 2, 4, 6, 8, 10, 12)
    assert profile_to_dict(profile) == original
    data['valve_bits'][0] = 15
    assert profile.valve_bits[0] == 0
    destination = tmp_path / 'operator-chosen.json'
    assert save_profile(destination, profile) == destination
    assert load_profile(destination, require_reviewed=True) == profile
    assert set(tmp_path.iterdir()) == {destination}


@pytest.mark.parametrize('changes', [
    {'profile_id': ''}, {'profile_id': 'UNVERIFIED'}, {'profile_id': 'a' * 65},
    {'profile_id': 'bad name'}, {'profile_id': 'bad"; #include <other>'},
    {'profile_id': '../unsafe'}, {'profile_id': 'unicode-\u03bb'},
    {'valve_bits': [0, 0, 2, 3, 4, 5, 6]}, {'valve_bits': [0, 1, 2, 3, 4, 5]},
    {'valve_bits': [0, 1, 2, 3, 4, 5, 16]}, {'valve_bits': [True, 1, 2, 3, 4, 5, 6]},
    {'valve_bits': [0.0, 1, 2, 3, 4, 5, 6]}, {'valve_bits': [[], 1, 2, 3, 4, 5, 6]},
    {'valve_bits': '0,1,2,3,4,5,6'}, {'rest_word': True}, {'rest_word': -1},
    {'rest_word': 65536}, {'rest_word': 0.0}, {'rest_word': '0'},
    {'mapping_verified': 1}, {'reviewed': 'true'}, {'extra_approval': True},
])
def test_untrusted_fields_cannot_generate_a_header(changes):
    with pytest.raises(ValueError):
        render_profile_header(reviewed_profile(**changes))


@pytest.mark.parametrize('missing', ['profile_id', 'valve_bits', 'rest_word', *REVIEW_FIELDS])
def test_every_field_must_be_explicit(missing):
    data = reviewed_profile()
    del data[missing]
    with pytest.raises(ValueError):
        validate_profile(data)


@pytest.mark.parametrize('flag', REVIEW_FIELDS)
def test_complete_unreviewed_draft_is_saveable_but_never_preparable(tmp_path, source_tree, flag):
    data = reviewed_profile(**{flag: False})
    target = tmp_path / 'draft.json'
    save_profile(target, data)
    assert not getattr(load_profile(target), flag)
    workspace = tmp_path / 'new workspace'
    with pytest.raises(ValueError, match='reviews'):
        prepare_workspace(source_tree, workspace, data)
    assert not workspace.exists()


def test_json_rejects_duplicates_oversize_and_non_objects(tmp_path):
    target = tmp_path / 'input.json'
    target.write_text('{"profile_id":"first","profile_id":"second"}', encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate'):
        load_profile(target)
    target.write_bytes(b' ' * (16 * 1024 + 1))
    with pytest.raises(ValueError, match='16 KiB'):
        load_profile(target)
    target.write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError):
        load_profile(target)


def test_drafts_never_overwrite_without_explicit_overwrite(tmp_path):
    target = tmp_path / 'chosen.json'
    target.write_text('KEEP MY DRAFT', encoding='utf-8')
    with pytest.raises(FileExistsError):
        save_profile(target, reviewed_profile())
    assert target.read_text() == 'KEEP MY DRAFT'
    save_profile(target, reviewed_profile(), overwrite=True)
    assert load_profile(target).profile_id == 'LAB-TEST-ONLY.1'


def test_generated_header_is_bounded_valve_only_and_preserves_exact_bits():
    header = render_profile_header(reviewed_profile())
    assert 'config.valveBits = {{0, 2, 4, 6, 8, 10, 12}};' in header
    assert 'config.restWord = 32769;' in header
    assert 'config.profileId = "LAB-TEST-ONLY.1";' in header
    assert 'config.resetOeSafeVerified = true;' in header
    assert 'config.pumpExcludedVerified = true;' in header
    assert 'BoardConfig' not in header and 'verifiedBoardConfig' not in header
    assert len(header) < 2048


def test_preparation_copies_only_allowlist_and_does_not_change_factory_source(tmp_path, source_tree):
    before = tree_bytes(source_tree)
    destination = tmp_path / 'private per-profile staging'
    result = prepare_workspace(source_tree, destination, reviewed_profile())
    assert result == destination
    assert tree_bytes(source_tree) == before
    assert set(tree_bytes(destination)) == set(SOURCE_FILES) | set(GENERATED_FILES)
    for name in SOURCE_FILES:
        assert (destination / name).read_bytes() == before[name]
    assert (destination / 'platformio.ini').read_text() == PLATFORMIO_INI
    assert 'espressif32@6.12.0' in PLATFORMIO_INI
    assert 'ArduinoJson@7.4.2' in PLATFORMIO_INI
    assert 'BASU_VALVE_PROFILE_HEADER=\\"ValveTestProfile.local.h\\"' in PLATFORMIO_INI
    assert 'BASU_VERIFIED_PROFILE_HEADER' not in PLATFORMIO_INI
    assert load_profile(destination / 'valve-profile.json', require_reviewed=True).rest_word == 32769


def test_plan_is_read_only(tmp_path, source_tree):
    before = tree_bytes(tmp_path)
    destination = tmp_path / 'planned workspace'
    plan = workspace_plan(source_tree, destination, reviewed_profile())
    assert plan['workspace'] == str(destination)
    assert plan['factory_source_modified'] is False
    assert tree_bytes(tmp_path) == before and not destination.exists()


@pytest.mark.parametrize('relation', ['same', 'descendant', 'ancestor', 'existing', 'missing_parent'])
def test_unsafe_workspace_relationships_never_modify_existing_paths(tmp_path, source_tree, relation):
    choices = dict(same=source_tree, descendant=source_tree / 'staging', ancestor=tmp_path,
                   existing=tmp_path / 'existing', missing_parent=tmp_path / 'absent' / 'stage')
    destination = choices[relation]
    if relation == 'existing':
        destination.mkdir()
        (destination / 'operator-data.txt').write_text('KEEP', encoding='utf-8')
    before = tree_bytes(tmp_path)
    with pytest.raises(ValueError):
        prepare_workspace(source_tree, destination, reviewed_profile())
    assert tree_bytes(tmp_path) == before


def test_missing_source_is_rejected_before_creating_workspace(tmp_path, source_tree):
    (source_tree / 'include/ValveTestCore.h').unlink()
    destination = tmp_path / 'no partial workspace'
    with pytest.raises(ValueError, match='Required firmware source'):
        prepare_workspace(source_tree, destination, reviewed_profile())
    assert not destination.exists()


def test_parent_traversal_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='traversal'):
        checked_path(tmp_path / '..' / 'other')


def test_junction_and_reparse_detection_do_not_need_link_creation_privilege(tmp_path, monkeypatch):
    target = tmp_path / 'pretend junction'
    target.mkdir()
    monkeypatch.setattr(Path, 'is_junction', lambda path: path == target, raising=False)
    with pytest.raises(ValueError, match='junctions'):
        checked_path(target / 'new workspace')
    monkeypatch.setattr(Path, 'is_junction', lambda _path: False)
    original = Path.lstat
    def marked_reparse(path):
        result = original(path)
        return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400) if path == target else result
    monkeypatch.setattr(Path, 'lstat', marked_reparse)
    with pytest.raises(ValueError, match='Reparse'):
        checked_path(target / 'new workspace')
    assert not (target / 'new workspace').exists()


@pytest.mark.parametrize('linked', ['source_file', 'source_folder', 'destination_parent', 'profile'])
def test_symbolic_links_are_rejected_without_writes(tmp_path, source_tree, linked):
    link = tmp_path / 'link'
    target = source_tree
    if linked == 'source_file':
        target = tmp_path / 'real.h'
        target.write_text('// keep', encoding='utf-8')
        link = source_tree / 'include/ValveTestCore.h'
        link.unlink()
    elif linked == 'profile':
        target = tmp_path / 'real.json'
        save_profile(target, reviewed_profile())
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip('This Windows account cannot create symbolic links.')
    with pytest.raises(ValueError, match='links|junctions|Reparse'):
        if linked == 'profile':
            load_profile(link)
        else:
            prepare_workspace(link if linked == 'source_folder' else source_tree,
                              link / 'stage' if linked == 'destination_parent' else tmp_path / 'stage',
                              reviewed_profile())
    assert not (tmp_path / 'stage').exists()


@pytest.fixture
def helper(monkeypatch):
    original = sys.dont_write_bytecode
    script = Path(__file__).resolve().parents[1] / 'packaging/prepare_valve_test.py'
    spec = importlib.util.spec_from_file_location('_test_prepare_valve_helper', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sys.dont_write_bytecode = original


def helper_args(tmp_path, source_tree):
    profile = tmp_path / 'operator profile.json'
    save_profile(profile, reviewed_profile())
    python = tmp_path / 'private tools' / 'python.exe'
    python.parent.mkdir()
    python.write_bytes(b'TEST DOUBLE ONLY')
    return ['--source-firmware', str(source_tree), '--profile', str(profile),
            '--workspace', str(tmp_path / 'build workspace'), '--python', str(python),
            '--core', str(tmp_path / 'separate pio cache')]


def test_cli_plan_never_creates_workspace_cache_or_runs_process(helper, tmp_path, source_tree, monkeypatch, capsys):
    args = helper_args(tmp_path, source_tree)
    before = tree_bytes(tmp_path)
    monkeypatch.setattr(helper.subprocess, 'run', lambda *_a, **_k: pytest.fail('Plan must not run tools'))
    assert helper.main(args + ['--port', 'COM4', '--upload', '--plan']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['upload_requires_typed_confirmation'] is True
    assert result['upload_command'][-2:] == ['--upload-port', 'COM4']
    assert tree_bytes(tmp_path) == before
    assert not (tmp_path / 'build workspace').exists()
    assert not (tmp_path / 'separate pio cache').exists()


def test_cli_plan_runs_in_isolated_python_without_qt_or_platformio_imports(tmp_path, source_tree):
    args = helper_args(tmp_path, source_tree)
    script = Path(__file__).resolve().parents[1] / 'packaging/prepare_valve_test.py'
    before = tree_bytes(tmp_path)
    result = subprocess.run([sys.executable, '-I', str(script), *args, '--plan'],
                            capture_output=True, text=True, check=False, timeout=15)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan['profile_id'] == 'LAB-TEST-ONLY.1' and plan['upload_command'] is None
    assert tree_bytes(tmp_path) == before
    assert not (tmp_path / 'build workspace').exists()
    assert not (tmp_path / 'separate pio cache').exists()


def test_cli_default_builds_only_with_argument_arrays(helper, tmp_path, source_tree, monkeypatch):
    args = helper_args(tmp_path, source_tree)
    calls = []
    monkeypatch.setattr(helper.subprocess, 'run', lambda argv, **kwargs: calls.append((argv, kwargs)))
    assert helper.main(args) == 0
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert isinstance(argv, list) and '-t' not in argv and '--upload-port' not in argv
    assert argv[1:6] == ['-I', '-m', 'platformio', '--no-ansi', 'run']
    assert kwargs['check'] is True and kwargs.get('shell', False) is False
    assert kwargs['env']['PLATFORMIO_CORE_DIR'] == str(tmp_path / 'separate pio cache')
    assert kwargs['cwd'] == tmp_path / 'build workspace'


@pytest.mark.parametrize('phrase,interactive,uploads', [
    ('UPLOAD VALVE TEST', True, 1), ('upload valve test', True, 0),
    ('yes', True, 0), ('UPLOAD VALVE TEST', False, 0),
])
def test_upload_requires_separate_exact_interactive_confirmation(helper, tmp_path, source_tree, monkeypatch, phrase, interactive, uploads):
    args = helper_args(tmp_path, source_tree)
    calls = []
    monkeypatch.setattr(helper.subprocess, 'run', lambda argv, **kwargs: calls.append(argv))
    monkeypatch.setattr(helper.sys.stdin, 'isatty', lambda: interactive)
    monkeypatch.setattr('builtins.input', lambda _prompt: phrase)
    assert helper.main(args + ['--upload', '--port', 'com4']) == 0
    assert len(calls) == 1 + uploads
    assert sum('--upload-port' in argv for argv in calls) == uploads
    if uploads:
        assert calls[-1][-4:] == ['-t', 'upload', '--upload-port', 'COM4']


@pytest.mark.parametrize('port', ['', 'COM0', 'COM01', 'COM4 & calc', '/dev/ttyUSB0', 'COM4;STOP'])
def test_upload_rejects_noncanonical_ports_before_staging(helper, tmp_path, source_tree, monkeypatch, port):
    args = helper_args(tmp_path, source_tree)
    monkeypatch.setattr(helper.subprocess, 'run', lambda *_a, **_k: pytest.fail('Invalid port must not build'))
    assert helper.main(args + ['--upload', '--port', port]) == 1
    assert not (tmp_path / 'build workspace').exists()


def test_build_failure_never_prompts_or_uploads_and_retains_staging(helper, tmp_path, source_tree, monkeypatch):
    args = helper_args(tmp_path, source_tree)
    calls = []
    def fail(argv, **_kwargs):
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)
    monkeypatch.setattr(helper.subprocess, 'run', fail)
    monkeypatch.setattr('builtins.input', lambda _prompt: pytest.fail('Failed build must not prompt to upload'))
    assert helper.main(args + ['--upload', '--port', 'COM4']) == 1
    assert len(calls) == 1 and '--upload-port' not in calls[0]
    assert (tmp_path / 'build workspace/platformio.ini').is_file()
