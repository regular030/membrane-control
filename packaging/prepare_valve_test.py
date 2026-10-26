"""Prepare/build an isolated reviewed valve target; upload only by typed consent."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # Even --plan must not leave helper/library caches.

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess


def _load_library():
    # Fixed trusted payload/repository locations; never import a venv namesake.
    directory = Path(__file__).resolve().parent
    choices = (directory / 'valve_profile.py',
               directory.parent / 'desktop/src/membrane_control/valve_profile.py')
    for path in choices:
        if path.is_file() and not path.is_symlink():
            spec = importlib.util.spec_from_file_location('_membrane_valve_profile_helper', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module
    raise RuntimeError('The valve-profile library is missing. Reinstall the complete tools payload.')


def canonical_port(value):
    port = (value or '').strip().upper()
    if not re.fullmatch(r'COM[1-9][0-9]{0,3}', port):
        raise ValueError('Select a Windows controller port such as COM4; no other command text is accepted.')
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-firmware', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--core', required=True)
    parser.add_argument('--port')
    parser.add_argument('--upload', action='store_true', help='Ask for typed confirmation after a successful build')
    parser.add_argument('--plan', action='store_true', help='Read-only validation; create nothing, run no tools and open no ports')
    args = parser.parse_args(argv)
    try:
        library = _load_library()
        profile = library.load_profile(args.profile, require_reviewed=True)
        plan = library.workspace_plan(args.source_firmware, args.workspace, profile)
        python = library.checked_path(args.python)
        core = library.checked_path(args.core)
        source = Path(plan['source_firmware'])
        if not python.is_file() or not re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)?)?(?:\.exe)?', python.name, re.IGNORECASE):
            raise ValueError('Choose the installed Python executable, such as tools/.venv/Scripts/python.exe.')
        if core.is_relative_to(source) or source.is_relative_to(core):
            raise ValueError('PlatformIO cache must be outside the shared firmware source tree.')
        workspace_path = Path(plan['workspace'])
        if core.is_relative_to(workspace_path) or workspace_path.is_relative_to(core):
            raise ValueError('PlatformIO cache and staging workspace must be separate directories.')
        if core.exists() and not core.is_dir():
            raise ValueError('PlatformIO cache path is not a directory.')
        port = canonical_port(args.port) if args.port or args.upload else None
        command = [str(python), '-I', '-m', 'platformio', '--no-ansi', 'run', '-d', plan['workspace'], '-e', 'esp32-valve-test']
        upload = command + ['-t', 'upload', '--upload-port', port] if args.upload else None
        if args.plan:
            print(json.dumps({**plan, 'build_command': command, 'upload_command': upload,
                              'platformio_core': str(core), 'upload_requires_typed_confirmation': bool(args.upload)}, indent=2))
            return 0
        print('VALVE-ONLY FIRMWARE. Factory source and production approvals remain unchanged.')
        print('Keep every relay COM/NO/NC load wire disconnected for this initial upload. Physically isolate the pump.')
        workspace = library.prepare_workspace(source, args.workspace, profile)
        core.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment['PLATFORMIO_CORE_DIR'] = str(core)
        print(f'Building reviewed profile {profile.profile_id} in {workspace}', flush=True)
        subprocess.run(command, cwd=workspace, env=environment, check=True)
        if not args.upload:
            print('Build complete. No serial port was opened or firmware uploaded.')
            return 0
        print(f'Upload would REPLACE firmware on {port}. Close the app and all other programs using that port.')
        print('Keep all relay contact loads disconnected and the pump physically isolated.')
        print('Three-wire UART: hold IO0, press/release EN, release IO0 before upload; reset afterward with IO0 released.')
        if not sys.stdin.isatty() or input('Type UPLOAD VALVE TEST to upload, or anything else to cancel: ') != 'UPLOAD VALVE TEST':
            print('Upload cancelled. Build retained; no serial port opened by this helper.')
            return 0
        subprocess.run(upload, cwd=workspace, env=environment, check=True)
        print('Upload finished. Release IO0 and briefly press EN/RESET, then reconnect in Valve test (no sensors).')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, EOFError) as error:
        print(f'Valve-test preparation stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
