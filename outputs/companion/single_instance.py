"""Keep one companion process per Windows login session, including portable builds."""
import ctypes
from ctypes import wintypes


MUTEX_NAME = r'Local\TFT-DataJ.Companion.v1'
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Hold a named Windows object until the event loop exits or startup fails."""

    def __init__(self, name=MUTEX_NAME):
        self.name = name
        self._handle = None
        self._kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self._kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        self._kernel.CreateMutexW.restype = wintypes.HANDLE
        self._kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel.CloseHandle.restype = wintypes.BOOL

    def acquire(self):
        if self._handle is not None:
            return True
        ctypes.set_last_error(0)
        handle = self._kernel.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        if error == ERROR_ALREADY_EXISTS:
            # A rejected launcher must not keep the original instance's lock alive.
            if not self._kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())
            return False
        self._handle = handle
        return True

    def close(self):
        if self._handle is not None:
            if not self._kernel.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()
