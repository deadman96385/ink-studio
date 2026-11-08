"""Keep GUI-initialized engine jobs off the user's interactive Windows desktop.

SVG tracing and live path effects still need GTK initialized. A small Win32
launcher routes them to this desktop without switching the user's desktop.
"""
import atexit
import os
import subprocess
import threading
import uuid

_lock = threading.Lock()
_desktop = None


class Desktop:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.api = c.WinDLL('user32', use_last_error=True)
        self.api.CreateDesktopW.argtypes = [w.LPCWSTR,w.LPCWSTR,c.c_void_p,w.DWORD,w.DWORD,c.c_void_p]
        self.api.CreateDesktopW.restype = w.HANDLE
        self.api.CloseDesktop.argtypes = [w.HANDLE]
        self.api.CloseDesktop.restype = w.BOOL
        self.name = 'InkStudio-engine-' + str(os.getpid()) + '-' + uuid.uuid4().hex[:12]
        # Desktop-specific rights only; default security stays with this user.
        self.handle = self.api.CreateDesktopW(self.name,None,None,0,0x01ff,None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        atexit.register(self.close)

    def close(self):
        if self.handle:
            self.api.CloseDesktop(self.handle)
            self.handle = None


def startup_info():
    global _desktop
    with _lock:
        if _desktop is None:_desktop = Desktop()
    info = subprocess.STARTUPINFO()
    info.dwFlags = subprocess.STARTF_USESHOWWINDOW | 0x00000080  # STARTF_FORCEOFFFEEDBACK
    info.wShowWindow = 0  # SW_HIDE, also useful to non-GTK child programs.
    return info


def name():
    startup_info()
    return _desktop.name
