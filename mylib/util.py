#!/usr/bin/env python3
# encoding=utf8
import json
import os
import shutil
import signal
import sys
import tempfile

if os.name == 'nt':
    from .nt_util import *
elif os.name == 'posix':
    from .posix_util import *
else:
    raise ImportError("Off-design OS: '{}'".format(os.name))


def legal_fs_name(x: str, repl: str or dict = None) -> str:
    if repl:
        if isinstance(repl, str):
            rl = len(repl)
            if rl > 1:
                legal = ILLEGAL_FS_CHARS_REGEX_PATTERN.sub(repl, x)
            elif rl == 1:
                legal = x.translate(str.maketrans(ILLEGAL_FS_CHARS, repl * ILLEGAL_FS_CHARS_LEN))
            else:
                legal = x.translate(str.maketrans('', '', ILLEGAL_FS_CHARS))
        elif isinstance(repl, dict):
            legal = x.translate(repl)
        else:
            raise ValueError("Invalid repl '{}'".format(repl))
    else:
        legal = x.translate(ILLEGAL_FS_CHARS_SUBSTITUTES_UNICODE_TABLE)
    return legal


def rename_helper(old_path: str, new: str, move_to: str = None, keep_ext: bool = True):
    old_root, old_basename = os.path.split(old_path)
    _, old_ext = os.path.splitext(old_basename)
    if move_to:
        new_path = os.path.join(move_to, new)
    else:
        new_path = os.path.join(old_root, new)
    if keep_ext:
        new_path = new_path + old_ext
    shutil.move(old_path, new_path)


def ensure_sigint_signal():
    if sys.platform == 'win32':
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # %ERRORLEVEL% = '-1073741510'


TEMPDIR = tempfile.gettempdir()


def real_join_path(path, *paths, expanduser: bool = True, expandvars: bool = True):
    """realpath(join(...))"""
    if expanduser:
        path = os.path.expanduser(path)
        paths = [os.path.expanduser(p) for p in paths]
    if expandvars:
        path = os.path.expandvars(path)
        paths = [os.path.expandvars(p) for p in paths]
    return os.path.realpath(os.path.join(path, *paths))


def ensure_open_file(file, mode='r', **kwargs):
    parent, basename = os.path.split(file)
    if not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    if not os.path.isfile(file):
        if os.path.exists(file):
            raise ValueError("Non-file already exists: {}".format(file))
        else:
            open(file, 'w', **kwargs).close()
    return open(file, mode, **kwargs)


def read_json_file(file, default=None, **kwargs):
    with ensure_open_file(file, 'r') as jf:
        try:
            d = json.load(jf, **kwargs)
        except json.decoder.JSONDecodeError:
            d = default or {}
    return d


def write_json_file(file, data, **kwargs):
    with ensure_open_file(file, 'w') as jf:
        json.dump(data, jf, **kwargs)