"""윈도우 시작 시 자동 실행 (HKCU Run 레지스트리).

관리자 권한 불필요 (현재 사용자 기준). 트레이 메뉴에서 on/off.
"""
from __future__ import annotations

import os
import sys
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "ClipAI"


def _command() -> str:
    """자동 실행에 등록할 명령 문자열."""
    if getattr(sys, "frozen", False):
        # 빌드된 exe
        return f'"{sys.executable}"'
    # 개발 모드: 콘솔 없는 pythonw 로 main.py 실행
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return f'"{pyw}" "{script}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            val, _ = winreg.QueryValueEx(key, _NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, _command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _NAME)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def toggle() -> bool:
    """상태를 뒤집고 새 상태(bool)를 반환."""
    if is_enabled():
        disable()
        return False
    enable()
    return True
