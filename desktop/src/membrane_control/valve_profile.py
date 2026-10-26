"""Validate reviewed valve-only profiles and stage isolated source workspaces.

This module opens no ports, runs no tools, and never changes factory firmware.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import stat


REVIEW_FIELDS = (
    'reviewed', 'mapping_verified', 'rest_word_verified', 'reset_oe_safe_verified',
    'solenoid_loads_verified', 'pump_excluded_verified',
)
PROFILE_FIELDS = frozenset(('profile_id', 'valve_bits', 'rest_word', *REVIEW_FIELDS))
SOURCE_FILES = (
    'compact_paths.py', 'include/ControlCore.h', 'include/StrictJson.h',
    'include/JsonRecipe.h', 'include/ValveTestConfig.h', 'include/ValveTestCore.h',
    'include/ValveTestHardware.h', 'include/ValveTestProfile.h', 'src/valve_test_main.cpp',
)
GENERATED_FILES = ('platformio.ini', 'include/ValveTestProfile.local.h', 'valve-profile.json')
MAX_PROFILE_BYTES = 16 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ValveProfile:
    profile_id: str
    valve_bits: tuple[int, ...]
    rest_word: int
    reviewed: bool
    mapping_verified: bool
    rest_word_verified: bool
    reset_oe_safe_verified: bool
    solenoid_loads_verified: bool
    pump_excluded_verified: bool


def validate_profile(data: dict | ValveProfile, *, require_reviewed: bool = False) -> ValveProfile:
    if isinstance(data, ValveProfile):
        data = asdict(data)
        data['valve_bits'] = list(data['valve_bits'])
    if type(data) is not dict or set(data) != PROFILE_FIELDS:
        raise ValueError('Profile must contain exactly the profile ID, seven bits, rest word and all six review flags.')
    profile_id = data['profile_id']
    if (not isinstance(profile_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', profile_id)
        or profile_id == 'UNVERIFIED'):
        raise ValueError('Profile ID must be 1-64 letters, digits, dash, underscore or dot; UNVERIFIED is reserved.')
    bits = data['valve_bits']
    if (type(bits) is not list or len(bits) != 7
        or any(type(bit) is not int or not 0 <= bit <= 15 for bit in bits)
        or len(set(bits)) != 7):
        raise ValueError('Choose seven distinct measured valve bits, each an integer from 0 to 15.')
    if type(data['rest_word']) is not int or not 0 <= data['rest_word'] <= 65535:
        raise ValueError('The measured rest word must be an integer from 0 to 65535.')
    if any(type(data[name]) is not bool for name in REVIEW_FIELDS):
        raise ValueError('Every review flag must be an explicit true or false value.')
    if require_reviewed and not all(data[name] for name in REVIEW_FIELDS):
        raise ValueError('All six valve-profile reviews must be completed before preparing firmware.')
    return ValveProfile(profile_id, tuple(bits), data['rest_word'], **{name: data[name] for name in REVIEW_FIELDS})


def profile_to_dict(profile: dict | ValveProfile) -> dict:
    result = asdict(validate_profile(profile))
    result['valve_bits'] = list(result['valve_bits'])
    return result


def checked_path(value: str | os.PathLike) -> Path:
    """Resolve a path only after rejecting symlinks/junctions in its chain."""
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ValueError('An explicit filesystem path is required.')
    path = Path(value).expanduser()
    if '..' in path.parts:
        raise ValueError('Use a path without parent-directory traversal.')
    path = path.absolute()
    try:
        for part in (*reversed(path.parents), path):
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise ValueError('Symbolic links and junctions are not allowed in profile/workspace paths.')
            if part.exists():
                attributes = getattr(part.lstat(), 'st_file_attributes', 0)
                if attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                    raise ValueError('Reparse points are not allowed in profile/workspace paths.')
        return path.resolve()
    except OSError as error:
        raise ValueError(f'Could not inspect filesystem path: {path}') from error


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON field: {key}')
        result[key] = value
    return result


def load_profile(path: str | os.PathLike, *, require_reviewed: bool = False) -> ValveProfile:
    source = checked_path(path)
    if not source.is_file() or source.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError('Profile JSON is missing or exceeds 16 KiB.')
    try:
        data = json.loads(source.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_keys)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Profile file must contain valid UTF-8 JSON.') from error
    return validate_profile(data, require_reviewed=require_reviewed)


def save_profile(path: str | os.PathLike, profile: dict | ValveProfile, *, overwrite: bool = False) -> Path:
    """Write a complete draft only at the caller's explicit chosen file path."""
    if type(overwrite) is not bool:
        raise ValueError('Overwrite must be an explicit true or false value.')
    content = json.dumps(profile_to_dict(profile), indent=2) + '\n'
    target = checked_path(path)
    if not target.parent.is_dir():
        raise ValueError('Choose an existing parent folder for the profile JSON.')
    with target.open('w' if overwrite else 'x', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    return target


def render_profile_header(profile: dict | ValveProfile) -> str:
    profile = validate_profile(profile, require_reviewed=True)
    bits = ', '.join(str(bit) for bit in profile.valve_bits)
    return f'''#pragma once
#include "ValveTestConfig.h"

// Generated from explicit reviewed JSON. Valve-only; never a production profile.
namespace basu {{
inline ValveTestConfig compiledValveTestConfig() {{
  ValveTestConfig config;
  config.profileId = "{profile.profile_id}";
  config.reviewed = true;
  config.mappingVerified = true;
  config.restWordVerified = true;
  config.resetOeSafeVerified = true;
  config.solenoidLoadsVerified = true;
  config.pumpExcludedVerified = true;
  config.valveBits = {{{{{bits}}}}};
  config.restWord = {profile.rest_word};
  return config;
}}
}}  // namespace basu
'''


PLATFORMIO_INI = '''[platformio]
default_envs = esp32-valve-test

[env:esp32-valve-test]
platform = espressif32@6.12.0
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps = bblanchon/ArduinoJson@7.4.2
build_unflags = -std=gnu++11
build_flags =
    -std=gnu++17
    -DBASU_VALVE_PROFILE_HEADER=\\"ValveTestProfile.local.h\\"
build_src_filter = -<*> +<valve_test_main.cpp>
extra_scripts = post:compact_paths.py
'''


def _workspace_inputs(source_firmware, destination, profile):
    profile = validate_profile(profile, require_reviewed=True)
    source, target = checked_path(source_firmware), checked_path(destination)
    if not source.is_dir():
        raise ValueError('Firmware source folder is missing.')
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError('Workspace must be separate from, and not an ancestor of, the shared firmware source.')
    if target.exists():
        raise ValueError('Workspace already exists. Choose a new folder; existing workspaces are never deleted or replaced.')
    if not target.parent.is_dir():
        raise ValueError('Workspace parent folder must already exist.')
    contents = {}
    for name in SOURCE_FILES:
        path = checked_path(source / name)
        if not path.is_relative_to(source) or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError(f'Required firmware source is missing, unsafe or too large: {name}')
        contents[name] = path.read_bytes()
    return profile, source, target, contents


def workspace_plan(source_firmware, destination, profile) -> dict:
    """Validate and describe a build without creating files or running tools."""
    profile, source, target, _ = _workspace_inputs(source_firmware, destination, profile)
    return dict(source_firmware=str(source), workspace=str(target), profile_id=profile.profile_id,
                source_files=list(SOURCE_FILES), generated_files=list(GENERATED_FILES),
                target='esp32-valve-test', factory_source_modified=False)


def prepare_workspace(source_firmware, destination, profile) -> Path:
    profile, _, target, contents = _workspace_inputs(source_firmware, destination, profile)
    # Exclusive creation: never reuse, clean, delete or replace a prior workspace.
    target.mkdir()
    for name, content in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (target / 'platformio.ini').write_text(PLATFORMIO_INI, encoding='utf-8')
    (target / 'include/ValveTestProfile.local.h').write_text(render_profile_header(profile), encoding='utf-8')
    (target / 'valve-profile.json').write_text(json.dumps(profile_to_dict(profile), indent=2) + '\n', encoding='utf-8')
    return target
