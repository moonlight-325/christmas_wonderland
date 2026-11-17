"""Windows API 래퍼 (ctypes). 비 Windows 에서는 빈 결과를 돌려준다.

 - 열린 창 / 작업표시줄 / 모니터 / 전체화면 앱 추적
 - 오버레이 창 스타일(클릭 통과, 항상 맨 아래, 작업 전환기 제외)
모든 함수는 예외를 삼키고 안전한 기본값을 반환한다 (오류가 프로그램을 죽이지 않도록).
"""
from __future__ import annotations

import os
import sys
import time

from .surfaces import WinEntry

IS_WINDOWS = sys.platform == "win32"

SWP_NOOWNERZORDER = 0x0200
WM_WINDOWPOSCHANGING = 0x0046

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    kernel32 = ctypes.windll.kernel32

    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    HWND_BOTTOM = 1
    HWND_TOP = 0
    HWND_TOPMOST = -1
    GW_HWNDFIRST = 0
    GW_HWNDLAST, GW_HWNDNEXT, GW_HWNDPREV = 1, 2, 3
    WS_EX_TOPMOST = 0x00000008
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    DWMWA_CLOAKED = 14

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                         ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    class APPBARDATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                    ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]

    shell32 = ctypes.windll.shell32
    shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
    shell32.SHAppBarMessage.restype = ctypes.c_size_t
    ABM_GETSTATE, ABM_GETTASKBARPOS = 4, 5
    ABS_AUTOHIDE, ABE_BOTTOM = 1, 3

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)]

    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND), ("x", ctypes.c_int),
                    ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wintypes.UINT)]

    _HWND_TOPMOST_V = ctypes.c_void_p(-1).value      # WINDOWPOS 에서 읽으면 부호 없는 값으로 보인다

SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "#32768",
                "tooltips_class32", "Windows.UI.Core.CoreWindow", "SysShadow"}
DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
OWN_PID = os.getpid()


# ---------------------------------------------------------------- 모니터
def get_monitors() -> dict:
    """{장치이름: (l, t, r, b)} 물리 픽셀. 장치이름은 QScreen.name() 과 같다 (예: \\\\.\\DISPLAY1)."""
    out: dict = {}
    if not IS_WINDOWS:
        return out
    try:
        def cb(hmon, hdc, lprc, lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                out[info.szDevice] = (r.left, r.top, r.right, r.bottom)
            return True
        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    except Exception:
        pass
    return out


_TB_T: dict = {}      # 마지막으로 작업표시줄을 읽은 시각
_TB_H: dict = {}      # 모니터 장치 이름 -> 마지막으로 확인한 아래쪽 작업표시줄 높이 (자동 숨김 중에도 기억)


def _taskbar_rects() -> list:
    """작업표시줄 사각형 [(l, t, r, b)]. 창 자체의 사각형과, 기본 작업표시줄이 '표시된 상태'의 사각형(ABM_GETTASKBARPOS)."""
    rects: list = []
    try:
        def cb(hwnd, lparam):
            try:
                if _class_name_raw(hwnd) in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                    r = wintypes.RECT()
                    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                        rects.append((r.left, r.top, r.right, r.bottom))
            except Exception:
                pass
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception:
        pass
    try:
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if hwnd:
            ad = APPBARDATA()
            ad.cbSize = ctypes.sizeof(APPBARDATA)
            ad.hWnd = hwnd
            if shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(ad)) and ad.uEdge == ABE_BOTTOM:
                rects.append((ad.rc.left, ad.rc.top, ad.rc.right, ad.rc.bottom))
    except Exception:
        pass
    return rects


def _taskbar_autohide() -> bool:
    try:
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if hwnd:
            ad = APPBARDATA()
            ad.cbSize = ctypes.sizeof(APPBARDATA)
            ad.hWnd = hwnd
            return bool(shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(ad)) & ABS_AUTOHIDE)
    except Exception:
        pass
    return False


def get_floors() -> dict:
    """{장치이름: 바닥 y} 물리 픽셀. 아래쪽 작업표시줄의 윗선, 없으면 모니터 아래 가장자리.

    - 작업 영역(rcWork)이 줄어 있으면 그 하단.
    - 작업표시줄이 '자동 숨김'이면 숨어 있을 때 작업 영역이 줄지 않으므로, 작업표시줄 창(또는 표시된 상태의 사각형) 높이만큼 올린다.
      (숨김 <-> 표시가 바뀌어도 바닥이 흔들리지 않게 마지막으로 확인한 높이를 기억해 둔다)
    """
    out: dict = {}
    if not IS_WINDOWS:
        return out
    try:
        bars = _taskbar_rects()
        autohide = _taskbar_autohide()

        def cb(hmon, hdc, lprc, lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                m, w = info.rcMonitor, info.rcWork
                dev = info.szDevice
                bottom = m.bottom
                # 작업 영역이 아래쪽만 줄었을 때(좌/우/위 작업표시줄이 아닐 때)만 바닥을 올린다
                if w.bottom < m.bottom and w.top == m.top and w.bottom > m.top + 200:
                    bottom = w.bottom
                h = 0
                for (tl, tt, tr, tb) in bars:
                    ht, wd = tb - tt, tr - tl
                    cx = (tl + tr) / 2
                    if (m.left <= cx < m.right and wd >= 3 * ht and 16 <= ht <= 300
                            and tt >= m.top + (m.bottom - m.top) // 2):
                        h = max(h, ht)
                if h:
                    _TB_H[dev] = h
                elif autohide and dev in _TB_H:
                    h = _TB_H[dev]
                else:
                    _TB_H.pop(dev, None)
                if h:
                    bottom = min(bottom, m.bottom - h)
                out[dev] = bottom
            return True
        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    except Exception:
        pass
    return out


def taskbar_height(mon, work, bars, autohide, remembered=0) -> int:
    """모니터 하나의 '아래쪽 작업표시줄 높이'(물리 픽셀, 없으면 0). 순수 계산 - Windows 호출 없음.

    우선순위: (1) 작업 영역(rcWork)이 아래쪽만 줄어 있으면 그 차이 (바탕화면/작업표시줄을 눌러도 바뀌지 않는 값)
              (2) 작업표시줄 창 사각형 (자동 숨김이어도 '표시된 상태' 사각형)
              (3) 둘 다 못 읽은 순간(클릭·전환 중)에는 마지막으로 확인한 높이를 그대로 유지한다 - 작업표시줄은 사라지지 않으므로
                  시간 제한을 두지 않는다. 단, 작업 영역이 다른 쪽(좌/우/위)만 줄어 있으면 작업표시줄이 옮겨간 것이므로 기억을 버린다.
    """
    ml, mt, mr, mb = mon
    moved_elsewhere = False
    if work is not None:
        wl, wt, wr, wb = work
        if wl == ml and wr == mr and wt == mt and mt + 200 < wb < mb:
            return int(mb - wb)
        moved_elsewhere = wl > ml or wr < mr or wt > mt
    h = 0
    for (tl, tt, tr, tb) in bars:
        ht, wd = tb - tt, tr - tl
        cx = (tl + tr) / 2
        if (ml <= cx < mr and wd >= 3 * ht and 16 <= ht <= 300 and tt >= mt + (mb - mt) // 2 and tb <= mb + 8):
            h = max(h, ht)
    if h:
        return int(h)
    if moved_elsewhere:
        return 0
    return int(remembered or 0)


def _monitor_work_areas() -> list:
    """[((모니터 사각형), (작업 영역 사각형))] 물리 픽셀."""
    out: list = []
    try:
        def cb(hmon, hdc, lprc, lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                m, w = info.rcMonitor, info.rcWork
                out.append(((m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom)))
            return True
        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    except Exception:
        pass
    return out


def floors_for_rects(rects: list) -> list:
    """모니터 사각형(물리 픽셀)마다 바닥 y (작업표시줄 윗선). 장치 이름이 아니라 '사각형' 으로 짝을 지어,
    Qt 의 화면 이름과 Windows 장치 이름이 달라도 작업표시줄을 놓치지 않는다. 작업표시줄이 없으면 모니터 아래 가장자리.
    계산 규칙은 taskbar_height 를 본다 (작업 영역 우선, 못 읽은 순간에는 마지막 값 유지)."""
    out = [float(r[3]) for r in rects]
    if not IS_WINDOWS:
        return out
    try:
        bars = _taskbar_rects()
        autohide = _taskbar_autohide()
        areas = _monitor_work_areas()
        for i, (ml, mt, mr, mb) in enumerate(rects):
            work = next((w for (m, w) in areas if tuple(m) == (ml, mt, mr, mb)), None)
            key = ("rect", ml, mt, mr, mb)
            h = taskbar_height((ml, mt, mr, mb), work, bars, autohide, _TB_H.get(key, 0))
            if h:
                _TB_H[key] = h
                _TB_T[key] = time.monotonic()
                out[i] = float(mb - h)
            else:
                _TB_H.pop(key, None)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- 창 추적
_STATIC_TTL = 30.0                 # 창 번호가 재사용돼도 이 시간(초) 안에는 바로잡힌다
_static: dict = {}                # hwnd -> (클래스 이름, 프로세스 번호): 창이 살아 있는 동안 바뀌지 않는 값
_static_t = 0.0
_cls_buf = None
_pid_buf = None


def _class_name_raw(hwnd) -> str:
    global _cls_buf
    if _cls_buf is None:
        _cls_buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, _cls_buf, 64)
    return _cls_buf.value


def _pid_raw(hwnd) -> int:
    global _pid_buf
    if _pid_buf is None:
        _pid_buf = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(_pid_buf))
    return _pid_buf.value


def _static_info(hwnd):
    """(클래스 이름, 프로세스 번호). 처음 한 번만 Win32 로 묻고 이후는 캐시에서 돌려준다."""
    global _static_t
    now = time.monotonic()
    if now - _static_t > _STATIC_TTL or len(_static) > 6000:
        _static.clear()
        _static_t = now
    key = int(hwnd or 0)
    v = _static.get(key)
    if v is None:
        v = (_class_name_raw(hwnd), _pid_raw(hwnd))
        _static[key] = v
    return v


def _class_name(hwnd) -> str:
    return _static_info(hwnd)[0]


def _pid(hwnd) -> int:
    return _static_info(hwnd)[1]


_rect_buf = None
_cloak_buf = None


def _frame_rect(hwnd):
    global _rect_buf
    if _rect_buf is None:
        _rect_buf = wintypes.RECT()
    r = _rect_buf
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r),
                                    ctypes.sizeof(r)) == 0:
        return r.left, r.top, r.right, r.bottom
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


def _is_cloaked(hwnd) -> bool:
    global _cloak_buf
    if _cloak_buf is None:
        _cloak_buf = ctypes.c_int(0)
    _cloak_buf.value = 0
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(_cloak_buf), 4) == 0:
        return _cloak_buf.value != 0
    return False


def snapshot_windows() -> list:
    """Z-order 위->아래 WinEntry 리스트 (작업표시줄 포함). 실패 시 빈 리스트."""
    if not IS_WINDOWS:
        return []
    entries: list = []
    seen: set = set()
    try:
        def cb(hwnd, lparam):
            try:
                seen.add(int(hwnd or 0))
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    return True
                cls = _class_name(hwnd)
                if cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                    r = wintypes.RECT()
                    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                        entries.append(WinEntry(("tb", int(hwnd or 0)), r.left, r.top, r.right,
                                                r.bottom, surface=True, taskbar=True))
                    return True
                if cls in SKIP_CLASSES or _is_cloaked(hwnd):
                    return True
                own = _pid(hwnd) == OWN_PID       # 우리 프로그램 창도 다른 창 위의 눈을 가린다 (눈은 쌓지 않음)
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if ex & WS_EX_TRANSPARENT:        # 클릭 통과 오버레이(다른 장식 프로그램 등)
                    return True
                rect = _frame_rect(hwnd)
                if rect is None:
                    return True
                surface = not own and not (ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)) \
                    and user32.GetWindowTextLengthW(hwnd) > 0
                entries.append(WinEntry(int(hwnd or 0), *rect, surface=surface, own=own))
            except Exception:
                pass
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception:
        return []
    if len(_static) > len(seen):                 # 이미 닫힌 창의 캐시는 버린다 (창 번호 재사용 대비)
        for k in [k for k in _static if k not in seen]:
            del _static[k]
    return entries


def fullscreen_monitors(monitor_rects: list) -> set:
    """전경 창이 모니터 전체를 덮는(게임/영상 전체화면) 모니터 인덱스 집합."""
    result: set = set()
    if not IS_WINDOWS:
        return result
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd or _class_name(hwnd) in DESKTOP_CLASSES or _pid(hwnd) == OWN_PID:
            return result
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return result
        for i, (ml, mt, mr, mb) in enumerate(monitor_rects):
            if r.left <= ml and r.top <= mt and r.right >= mr and r.bottom >= mb:
                result.add(i)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------- 오버레이 창 스타일
def make_overlay_window(hwnd: int) -> bool:
    """클릭 통과 + 레이어드 + 비활성 + 도구창(작업 전환기 제외) + 항상 맨 아래(다른 모든 창 뒤, 바탕화면 위)."""
    if not IS_WINDOWS:
        return False
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        want = ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if want != ex:                                  # 이미 적용돼 있으면 다시 쓰지 않는다 (불필요한 스타일 변경 메시지 방지)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, want)
        return keep_bottom(hwnd)
    except Exception:
        return False


def _insert_after_target(hwnd: int):
    """장식/눈 창이 들어갈 Z-order 위치(이 창보다 '바로 뒤'에 놓을 기준 창)를 구한다.

    바탕화면(Progman/WorkerW), 항상 위 창, 우리 프로그램 창을 제외한 '가장 아래의 일반 창' 을 찾는다.
    그 바로 뒤 = 바탕화면 바로 위. HWND_BOTTOM 을 그대로 쓰면 바탕화면 창 뒤로 내려가 가려질 수 있다.
    일반 창이 없으면 None.
    """
    try:
        h = user32.GetWindow(hwnd, GW_HWNDLAST)
        guard = 0
        while h and guard < 3000:
            guard += 1
            if (h != hwnd and _class_name_raw(h) not in DESKTOP_CLASSES and _pid_raw(h) != OWN_PID
                    and not (user32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOPMOST)):
                return h
            h = user32.GetWindow(h, GW_HWNDPREV)
    except Exception:
        pass
    return None


def _is_below(hwnd: int, ref: int) -> bool:
    """hwnd 가 Z-order 에서 ref 보다 아래에 있는가."""
    try:
        h = ref
        guard = 0
        while h and guard < 3000:
            guard += 1
            h = user32.GetWindow(h, GW_HWNDNEXT)
            if h == hwnd:
                return True
    except Exception:
        pass
    return False


def _desktop_above(hwnd: int) -> bool:
    """보이는 바탕화면 창(Progman/WorkerW)이 hwnd 보다 위에 있는가.
    바탕화면을 클릭하면 바탕화면 창이 앞으로 올라와 바닥에 깔아 둔 눈 오버레이를 덮어 버린다."""
    try:
        h = user32.GetWindow(hwnd, GW_HWNDPREV)
        guard = 0
        while h and guard < 3000:
            guard += 1
            if _class_name_raw(h) in ("Progman", "WorkerW") and user32.IsWindowVisible(h):
                return True
            h = user32.GetWindow(h, GW_HWNDPREV)
    except Exception:
        pass
    return False


def _above_desktop_target(hwnd: int):
    """일반 창이 하나도 없을 때: 가장 위에 있는 바탕화면 창 바로 위에 들어갈 기준 창.
    (HWND_BOTTOM 은 바탕화면 창 '뒤' 로 내려가 눈이 통째로 가려진다.) 바탕화면 창이 없으면 None."""
    try:
        prev = None
        h = user32.GetWindow(hwnd, GW_HWNDFIRST)
        guard = 0
        while h and guard < 3000:
            guard += 1
            if h != hwnd and _class_name_raw(h) in ("Progman", "WorkerW") and user32.IsWindowVisible(h):
                return prev if prev is not None else HWND_TOP
            if h != hwnd:
                prev = h
            h = user32.GetWindow(h, GW_HWNDNEXT)
    except Exception:
        pass
    return None


def keep_bottom(hwnd: int, rect=None) -> bool:
    """창을 항상 모든 일반 창의 맨 아래(바탕화면 바로 위)에 둔다 (활성화 없음).

    rect=(l, t, r, b) 를 주면 위치/크기도 함께 맞춘다. 이미 올바른 위치에 있으면 Z-order 를 다시 건드리지 않아
    같은 층의 여러 창(눈 오버레이, 장식 등)이 서로 앞뒤를 바꾸며 깜빡이지 않는다.
    바탕화면 창이 위로 올라와 있으면(바탕화면 클릭) 이미 '일반 창 뒤' 여도 다시 바탕화면 위로 올린다.
    """
    if not IS_WINDOWS:
        return False
    try:
        ref = _insert_after_target(hwnd)
        ok = (ref is not None and _is_below(hwnd, ref)) and not _desktop_above(hwnd)
        flags = SWP_NOACTIVATE
        if rect is None:
            if ok:
                return True
            flags |= SWP_NOMOVE | SWP_NOSIZE
            l = t = w = h = 0
        else:
            l, t, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
            if ok:
                flags |= SWP_NOZORDER
        after = ref if ref is not None else _above_desktop_target(hwnd)
        if after is None:
            after = HWND_BOTTOM
        if not (flags & SWP_NOZORDER):
            STAT["bottom_moves"] += 1
        return bool(user32.SetWindowPos(hwnd, after, l, t, w, h, flags))
    except Exception:
        return False


_TOP_OVERLAYS: set = set()
# 진단용 누적값. bottom_moves: 바닥 오버레이/장식을 실제로 옮긴 횟수, top_moves: 항상 위 층(눈 오버레이·장식)의 SetWindowPos 횟수,
# top_checks: 항상 위 층 점검 횟수, top_fixes: 점검 중 실제로 보정이 필요했던 횟수, top_repeats: 같은 창을 곧바로 다시 보정한 횟수,
# top_intercepts: WM_WINDOWPOSCHANGING 에서 작업표시줄 앞으로 올라오려던 것을 바로잡은 횟수
STAT = {"bottom_moves": 0, "top_moves": 0}
_HOOKS: list = []          # 콜백 참조 유지 (가비지 컬렉션 방지)
_FG_LISTENERS: list = []   # 전경 창 변경 알림을 받을 함수들 (눈 엔진, 장식 창 층 관리)
_DECOR_PROVIDER = None     # 함수: 항상 위 층 장식 창의 HWND 목록을 돌려준다 (decor.layer 가 등록)


def taskbar_rects() -> list:
    """작업표시줄 사각형 목록 (창 추적 설정과 무관하게 쓰는 공개 함수)."""
    if not IS_WINDOWS:
        return []
    return _taskbar_rects()


def install_foreground_hook(callback) -> bool:
    """활성 창이 바뀔 때(바탕화면/작업표시줄 클릭 포함) callback() 을 호출한다. Qt 메시지 루프 스레드에서 실행된다.
    후크는 한 번만 설치하고, 여러 곳(눈 엔진, 장식 창 층 관리)이 각자 callback 을 등록할 수 있다."""
    if not IS_WINDOWS:
        return False
    if callback not in _FG_LISTENERS:
        _FG_LISTENERS.append(callback)
    if _HOOKS:
        return True
    try:
        proto = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                   wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def _cb(hook, event, hwnd, idobj, idchild, tid, ts):
            for fn in list(_FG_LISTENERS):
                try:
                    fn()
                except Exception:
                    pass

        fn = proto(_cb)
        user32.SetWinEventHook.restype = wintypes.HANDLE
        user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, proto,
                                           wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT = 3, 0
        h = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, fn, 0, 0,
                                   WINEVENT_OUTOFCONTEXT)
        if h:
            _HOOKS.append((h, fn))
            return True
    except Exception:
        pass
    return False


def make_top_overlay(hwnd: int) -> bool:
    """장식 위에 눈을 덧그리는 오버레이: 클릭 통과 + 레이어드 + 비활성 + 도구창 + 항상 위.
    (그리는 범위는 장식 창이 보이는 부분으로만 제한된다 - 일반 창 위에는 눈이 그려지지 않는다.)
    Z-order 는 항상 위 층 규칙(작업표시줄 > 눈 오버레이 > 항상 위 장식 창)에 맞춰 settle_topband 가 잡는다."""
    if not IS_WINDOWS:
        return False
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        want = ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if want != ex:                                  # 이미 적용돼 있으면 다시 쓰지 않는다 (불필요한 스타일 변경 메시지 방지)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, want)
        return keep_top(hwnd)
    except Exception:
        return False


# ---------------------------------------------------------------- 항상 위 층 Z-order (눈 오버레이 > 장식)
#
# 항상 위(TOPMOST) 층에서는 top 눈 오버레이가 항상 항상 위 장식 창들보다 앞에 있어야 장식 위에 눈이 보인다:
#
#     top 눈 오버레이(들)  >  항상 위 장식 창들  >  (다른 창)
#
# 작업표시줄과의 관계는 여기서 다루지 않는다 (오버레이는 작업표시줄 윗선까지만 덮고, 장식은 그 선 아래를 가린다 - decor.layer).
# 이미 규칙에 맞으면 SetWindowPos 를 부르지 않는다. 어긋난 오버레이만 옮긴다.
def plan_topband(ov_pos: dict, dc_pos: dict) -> list:
    """눈 오버레이가 장식보다 뒤에 있을 때 앞으로 올릴 오버레이 목록 [("overlay", hwnd)] (순수 계산, Windows 호출 없음).
    ov_pos / dc_pos: {hwnd: Z-order 위치(0 이 맨 위)}. 아래에 있던 것부터 올려 나중 것이 위에 온다."""
    if not dc_pos:
        return []
    top_dc = min(dc_pos.values())
    bad = sorted((h for h, p in ov_pos.items() if p > top_dc), key=lambda h: -ov_pos[h])
    return [("overlay", h) for h in bad]


def set_decor_provider(fn) -> None:
    """항상 위 층 장식 창의 HWND 목록을 돌려주는 함수를 등록한다 (decor.layer 가 한 번 호출)."""
    global _DECOR_PROVIDER
    _DECOR_PROVIDER = fn


if IS_WINDOWS:
    def _z_positions(wanted: set) -> dict:
        """{hwnd: Z-order 위치(0 이 맨 위)} - wanted 에 든 창만. 맨 위에서 한 번만 훑고, 다 찾으면 멈춘다."""
        out: dict = {}
        if not wanted:
            return out
        h = user32.GetWindow(next(iter(wanted)), GW_HWNDFIRST)
        i = 0
        while h and i < 4000:
            hv = int(h)
            if hv in wanted:
                out[hv] = i
                if len(out) == len(wanted):
                    break
            i += 1
            h = user32.GetWindow(h, GW_HWNDNEXT)
        return out

    def _live_top_overlays() -> list:
        alive = [h for h in list(_TOP_OVERLAYS) if user32.IsWindow(h)]
        _TOP_OVERLAYS.intersection_update(alive)             # 다시 만들어져 사라진 오버레이 HWND 정리 (HWND 재사용 오인 방지)
        return [h for h in alive if user32.IsWindowVisible(h)]

    def _live_top_decor() -> list:
        try:
            hs = list(_DECOR_PROVIDER() or []) if _DECOR_PROVIDER is not None else []
        except Exception:
            return []
        return [int(h) for h in hs if user32.IsWindow(h) and user32.IsWindowVisible(h)]

    def _place_top(hwnd: int) -> bool:
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
        return bool(user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags))

    def settle_topband(reason: str = "check"):
        """눈 오버레이가 장식 창보다 앞인지 한 번 훑어 확인하고, 어긋난 오버레이만 옮긴다.

        반환: None = 관리할 창이 없음, [] = 이미 올바름(아무것도 안 바꿈), [(역할, hwnd), ...] = 옮긴 목록.
        이벤트(전경 창 변경, 장식 창 표시, 화면 구성 변경)와 느린 안전망에서만 호출한다 - 프레임마다 부르지 않는다.
        """
        try:
            ovs, decs = _live_top_overlays(), _live_top_decor()
            if not ovs and not decs:
                return None
            pos = _z_positions(set(ovs) | set(decs))
            plan = plan_topband({h: pos[h] for h in ovs if h in pos}, {h: pos[h] for h in decs if h in pos})
            done: list = []
            for role, h in plan:
                if _place_top(h):
                    done.append((role, h))
                    STAT["top_moves"] += 1
            return done
        except Exception:
            return None

    def keep_decor_below_overlay(message) -> bool:
        """항상 위 장식 창의 nativeEvent 에서 호출. 클릭 활성화나 Qt 의 TOPMOST 재지정으로 장식 창이 '맨 위' 로 올라오려는 순간
        (WM_WINDOWPOSCHANGING) 삽입 위치를 눈 오버레이 바로 뒤로 바꿔, 장식이 눈 오버레이 앞으로 올라왔다 내려가는 깜빡임을 막는다.
        특정 창 뒤로 지정된 요청(우리 보정 포함)과 Z-order 를 건드리지 않는 요청은 그대로 둔다."""
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message != WM_WINDOWPOSCHANGING or not msg.lParam:
                return False
            wp = WINDOWPOS.from_address(msg.lParam)
            if wp.flags & SWP_NOZORDER:
                return False
            if int(wp.hwndInsertAfter or 0) not in (0, _HWND_TOPMOST_V):
                return False
            ovs = _live_top_overlays()
            if not ovs:
                return False
            pos = _z_positions(set(ovs))
            if not pos:
                return False
            target = max(pos, key=pos.get)             # 가장 아래에 있는 눈 오버레이 바로 뒤
            if target == int(msg.hWnd or 0):
                return False
            wp.hwndInsertAfter = target
            return True
        except Exception:
            return False

else:
    def settle_topband(reason: str = "check"):
        return None

    def keep_decor_below_overlay(message) -> bool:
        return False


def keep_top(hwnd: int) -> bool:
    """top 눈 오버레이를 항상 위 층 규칙(눈 오버레이 > 장식)에 맞춘다. 이미 맞으면 아무것도 바꾸지 않는다."""
    if not IS_WINDOWS:
        return False
    _TOP_OVERLAYS.add(int(hwnd))
    settle_topband("overlay-shown")
    return True


_NOT_OCCLUDERS = ("Progman", "WorkerW", "tooltips_class32", "SysShadow", "IME", "MSCTFIME UI")


def occluders_above(hwnd: int) -> list:
    """hwnd 보다 Z-order 에서 위에 있는, 눈을 가려야 하는 다른 프로그램의 창 사각형 목록 [(l, t, r, b)].
    우리 프로그램 창(다른 장식 포함)과 클릭 통과 오버레이, 보이지 않는 창, 제목 없는 보조 창은 제외한다."""
    out: list = []
    if not IS_WINDOWS:
        return out
    try:
        h = user32.GetWindow(hwnd, GW_HWNDPREV)
        guard = 0
        while h and guard < 3000:
            guard += 1
            try:
                if (user32.IsWindowVisible(h) and not user32.IsIconic(h) and _pid(h) != OWN_PID
                        and _class_name(h) not in _NOT_OCCLUDERS
                        and not _is_cloaked(h)):
                    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
                    if not ((ex & WS_EX_TRANSPARENT) or ((ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE))
                                                         and user32.GetWindowTextLengthW(h) == 0)):
                        r = _frame_rect(h)
                        if r is not None and (r[2] - r[0]) >= 8 and (r[3] - r[1]) >= 8:
                            out.append(r)
            except Exception:
                pass
            h = user32.GetWindow(h, GW_HWNDPREV)
    except Exception:
        pass
    return out


def cursor_pos():
    """마우스 커서의 가상 데스크톱 물리 픽셀 좌표 (x, y). Windows 가 아니면 None."""
    if not IS_WINDOWS:
        return None
    try:
        pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


def left_button_down() -> bool:
    """마우스 왼쪽 버튼이 눌려 있는가 (전역). 오버레이는 클릭이 통과하므로 눈덩이 잡기는 이 값을 직접 읽는다.
    Windows 가 아니면 False (Qt 의 QGuiApplication.mouseButtons 로 대체)."""
    if not IS_WINDOWS:
        return False
    try:
        swapped = user32.GetSystemMetrics(23)          # SM_SWAPBUTTON
        vk = 0x02 if swapped else 0x01                 # 물리 왼쪽 버튼이 아니라 '주 버튼'
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def window_rect(hwnd: int):
    """창의 실제 물리 픽셀 사각형 (l, t, r, b) 또는 None."""
    if not IS_WINDOWS:
        return None
    try:
        r = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return None


def set_window_rect(hwnd: int, rect, top: bool = False) -> bool:
    if top:
        if not IS_WINDOWS:
            return False
        try:
            # 위치/크기만 바꾼다. 예전에는 HWND_TOPMOST 로 다시 올렸지만 그러면 작업표시줄 앞으로 올라온다 (Z-order 는 settle_topband 담당)
            return bool(user32.SetWindowPos(hwnd, 0, rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1],
                                            SWP_NOACTIVATE | SWP_NOZORDER | SWP_NOOWNERZORDER))
        except Exception:
            return False
    return keep_bottom(hwnd, rect)
