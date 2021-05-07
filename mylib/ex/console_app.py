#!/usr/bin/env python3
from mylib.easy import *
from mylib.easy.argparse import *
from mylib.ex import fstk
from mylib.ex import ostk


def __ref():
    return fstk


PathSourceTypeTuple = list, str, T.NoneType
PathSourceType = T.Union[T.List[str], str, T.NoneType]

stderr_print = functools.partial(print, file=sys.stderr)


def resolve_path_to_dirs_files(x: PathSourceType, *,
                               use_clipboard=True, use_stdin=False,
                               glob_recurse=False, exist_prior_to_glob=True):
    if not isinstance(x, PathSourceTypeTuple):
        raise TypeError('src', PathSourceType)

    if not x:
        if use_clipboard:
            xl = ostk.clipboard.list_path()
        else:
            return [], []
    elif use_stdin and x in ('-', ['-']):
        xl = sys.stdin.read().splitlines()
    else:
        if isinstance(x, list):
            xl = x
        else:
            xl = [x]
    return glob_or_exist_to_dirs_files(xl, glob_recurse=glob_recurse, exist_prior_to_glob=exist_prior_to_glob)