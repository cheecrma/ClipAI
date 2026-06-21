"""전역 단축키 등록/해제 (keyboard 라이브러리).

권한/충돌 이슈가 있으면 win32 RegisterHotKey 로 교체 가능 (§12).
"""
from __future__ import annotations

import keyboard


class HotkeyManager:
    def __init__(self, mapping: dict, on_trigger):
        """mapping: {mode: "ctrl+alt+a", ...}, on_trigger: callable(mode)."""
        self.mapping = mapping
        self.on_trigger = on_trigger
        self._handles = []

    def register(self):
        for mode, combo in self.mapping.items():
            h = keyboard.add_hotkey(
                combo, self.on_trigger, args=(mode,),
                suppress=False, trigger_on_release=False,
            )
            self._handles.append(h)
            print(f"[hotkeys] {combo} -> {mode}")

    def unregister(self):
        for h in self._handles:
            try:
                keyboard.remove_hotkey(h)
            except Exception:  # noqa: BLE001
                pass
        self._handles.clear()
