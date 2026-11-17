"""Windows Z-order 제어 (항상 아래 창).

방식:
 1) SetWindowPos(HWND_BOTTOM, NOACTIVATE) 로 창을 맨 뒤로 보낸다.
 2) WM_WINDOWPOSCHANGING 을 가로채 hwndInsertAfter 를 HWND_BOTTOM 으로 고정한다.
    -> 위젯을 클릭(활성화)해도 일반 창 위로 올라오지 않는다.
 3) 주기적으로 한 번 더 맨 뒤로 보내는 보정 타이머는 MainWidget 쪽에서 실행한다.
항상 위(TOPMOST)는 사용하지 않는다.
"""
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    HWND_BOTTOM = 1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    WM_WINDOWPOSCHANGING = 0x0046
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    SWP_FRAMECHANGED = 0x0020

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("hwndInsertAfter", wintypes.HWND),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("cx", ctypes.c_int),
            ("cy", ctypes.c_int),
            ("flags", wintypes.UINT),
        ]

    _user32 = ctypes.windll.user32
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _get_window_long = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _set_window_long = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long.restype = ctypes.c_ssize_t
    _set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_window_long.restype = ctypes.c_ssize_t


def set_taskbar_visible(widget, visible: bool) -> bool:
    """메인 위젯의 작업표시줄 버튼만 표시/숨김 처리한다 (창 유형과 Z-order 는 유지)."""
    if not IS_WINDOWS:
        return False
    try:
        hwnd = int(widget.winId())
        style = int(_get_window_long(hwnd, GWL_EXSTYLE))
        if visible:
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        else:
            style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
        _set_window_long(hwnd, GWL_EXSTYLE, style)
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        return bool(_user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags))
    except Exception:
        return False


def send_to_bottom(widget) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        hwnd = int(widget.winId())
        # 눈 오버레이와 같은 규칙(바탕화면 바로 위, 이미 그 자리면 Z-order 를 건드리지 않음)을 써서
        # 주기 보정 때마다 두 창이 앞뒤를 바꾸며 깜빡이는 것을 막는다.
        try:
            from snow import winapi as _snow_winapi
            return bool(_snow_winapi.keep_bottom(hwnd))
        except Exception:
            pass
        return bool(_user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))
    except Exception:
        return False


def force_bottom_on_message(message) -> None:
    """nativeEvent 에서 호출. WM_WINDOWPOSCHANGING 의 Z-order 를 맨 뒤로 고정."""
    if not IS_WINDOWS:
        return
    try:
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_WINDOWPOSCHANGING and msg.lParam:
            wp = WINDOWPOS.from_address(msg.lParam)
            # 활성화(클릭) 등으로 Z-order 변경이 요청된 경우에만 개입: 현재 순서를 그대로 유지시킨다.
            # (이동/크기 변경마다 HWND_BOTTOM 으로 강제 재배치하던 것이 깜빡임의 원인)
            if not (wp.flags & SWP_NOZORDER):
                wp.flags |= SWP_NOZORDER
    except Exception:
        pass


def force_foreground(widget) -> bool:
    """일반 창을 확실히 맨 앞으로 가져온다 (Windows 의 포그라운드 잠금 우회).

    Qt 의 raise_/activateWindow 만으로는 다른 프로세스가 포그라운드일 때 작업표시줄만 깜빡이고
    창이 앞으로 오지 않을 수 있어서, 최소화 복원 -> 잠깐 TOPMOST -> 입력 스레드 연결 후 SetForegroundWindow 순으로 처리한다.
    """
    if not IS_WINDOWS:
        return False
    try:
        u = _user32
        hwnd = int(widget.winId())
        SW_RESTORE, SW_SHOW = 9, 5
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        flags = SWP_NOMOVE | SWP_NOSIZE
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, SW_RESTORE)
        else:
            u.ShowWindow(hwnd, SW_SHOW)
        u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        fg = u.GetForegroundWindow()
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_tid = u.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = bool(fg_tid and fg_tid != cur_tid and u.AttachThreadInput(fg_tid, cur_tid, True))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(fg_tid, cur_tid, False)
        return True
    except Exception:
        return False
