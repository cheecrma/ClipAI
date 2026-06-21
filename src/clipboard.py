"""선택 텍스트 캡처.

Ctrl+C 시뮬레이션 후 클립보드 폴링으로 선택 영역을 읽고,
원래 클립보드 내용을 복원한다.

센티넬 기법: 복사 직전 클립보드를 고유 문자열로 덮어쓴 뒤
Ctrl+C 를 보내고, 클립보드가 센티넬에서 '바뀌면' 그게 선택 텍스트다.
→ 스테일(이전) 클립보드 값을 잘못 읽는 문제를 방지.
"""
from __future__ import annotations

import time
import pyperclip
import keyboard

_SENTINEL = "\x00__CLIPAI_EMPTY__\x00"


def _safe_paste() -> str:
    try:
        return pyperclip.paste()
    except Exception:  # noqa: BLE001
        return ""


def _safe_copy(text: str) -> None:
    try:
        pyperclip.copy(text)
    except Exception:  # noqa: BLE001
        pass


def capture_selection(restore: bool = True, timeout_ms: int = 350) -> str:
    """드래그 선택된 텍스트를 반환. 캡처 실패 시 빈 문자열."""
    original = _safe_paste()

    # 단축키 조합(ctrl+alt)이 눌린 상태면 Ctrl+C 가 오작동 → 모디파이어 해제.
    for key in ("alt", "ctrl", "shift"):
        try:
            keyboard.release(key)
        except Exception:  # noqa: BLE001
            pass
    time.sleep(0.03)

    _safe_copy(_SENTINEL)
    try:
        keyboard.send("ctrl+c")
    except Exception:  # noqa: BLE001
        pass

    deadline = time.time() + timeout_ms / 1000.0
    captured = ""
    while time.time() < deadline:
        cur = _safe_paste()
        if cur and cur != _SENTINEL:
            captured = cur
            break
        time.sleep(0.02)

    if restore:
        _safe_copy(original)

    return captured.strip()


def set_clipboard(text: str) -> None:
    """결과를 클립보드에 복사 (팝업 [복사] 버튼용)."""
    _safe_copy(text)
