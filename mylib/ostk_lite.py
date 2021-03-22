#!/usr/bin/env python3
# encoding=utf8
import signal
from io import FileIO

from .ez import *
from . import tricks_lite


def __refer_sth_do_not_use_this():
    return tricks_lite


def ensure_sigint_signal():
    if sys.platform == 'win32':
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # %ERRORLEVEL% = '-1073741510'


class SubscriptableFileIO(FileIO):
    """slice data in FileIO object"""

    def __init__(self, file, mode='rb', *args, **kwargs):
        """refer to doc string of io.FileIO"""
        super(SubscriptableFileIO, self).__init__(file, mode=mode, *args, **kwargs)
        try:
            self._size = os.path.getsize(file)
        except TypeError:
            self._size = os.path.getsize(self.name)

    def __len__(self):
        return self._size

    @property
    def size(self):
        return self._size

    def __getitem__(self, key: int or slice):
        orig_pos = self.tell()
        if isinstance(key, int):
            if key < 0:
                key = self.size + key
            self.seek(key)
            r = self.read(1)
        elif isinstance(key, slice):
            start, stop, step = key.start, key.stop, key.step
            if not start:
                start = 0
            elif start < 0:
                start = self.size + start
            if not stop:
                stop = self.size
            elif stop < 0:
                stop = self.size + stop
            size = stop - start
            if size <= 0:
                r = b''
            elif not step or step == 1:
                self.seek(start)
                r = self.read(size)
            else:
                r = self.read(size)[::step]
        else:
            raise TypeError("'{}' is not int or slice".format(key))
        self.seek(orig_pos)
        return r

    def __setitem__(self, key: int or slice, value: bytes):
        orig_pos = self.tell()
        value_len = len(value)

        if isinstance(key, int):
            if value_len != 1:
                raise ValueError("overflow write", value)
            if key < 0:
                key = self.size + key
            self.seek(key)
            self.write(value)
        elif isinstance(key, slice):
            if key.step not in (None, 1):
                raise NotImplementedError('non-sequential write')
            start, stop = key.start, key.stop
            if not start and not stop:
                self.truncate(value_len)
                start = stop = 0
                slice_len = value_len
            else:
                start = start or 0
                if start < 0:
                    start += self._size
                stop = stop or 0
                if stop < 0:
                    stop += self._size
                slice_len = stop - start
            if value_len <= slice_len:
                self.seek(start)
                self.write(value)
                self._size = max(self.size, start + value_len)
            else:
                raise NotImplementedError('overflow write')
        else:
            raise TypeError("'{}' is not int or slice".format(key))
        self.seek(orig_pos)