"""트레이 아이콘/메뉴 (pystray + Pillow).

별도 데몬 스레드에서 실행 (tk 메인루프와 분리).
메뉴: 모델명(비활성) · 엔진 재워밍 · 종료.
"""
from __future__ import annotations

import threading

import pystray
from PIL import Image, ImageDraw

import autostart


def _make_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 둥근 다크 사각형
    d.rounded_rectangle([4, 4, 60, 60], radius=14, fill=(28, 28, 32, 255),
                        outline=(108, 140, 255, 255), width=2)
    # 클립보드 클립 + 'AI'
    d.rounded_rectangle([24, 8, 40, 16], radius=3, fill=(108, 140, 255, 255))
    d.text((16, 26), "AI", fill=(236, 236, 240, 255))
    return img


class Tray:
    def __init__(self, engine_name: str, on_quit, on_rewarm):
        self.on_quit = on_quit
        self.on_rewarm = on_rewarm
        menu = pystray.Menu(
            pystray.MenuItem(engine_name, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "윈도우 시작 시 자동 실행",
                lambda: autostart.toggle(),
                checked=lambda item: autostart.is_enabled(),
            ),
            pystray.MenuItem("엔진 재워밍", lambda: self.on_rewarm()),
            pystray.MenuItem("종료", lambda: self._quit()),
        )
        self.icon = pystray.Icon("ClipAI", _make_icon(), "ClipAI", menu)

    def _quit(self):
        self.icon.stop()
        self.on_quit()

    def run_detached(self):
        t = threading.Thread(target=self.icon.run, daemon=True)
        t.start()
        return t
