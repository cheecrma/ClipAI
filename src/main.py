"""ClipAI 진입점.

트레이 + 전역 단축키 + LLM 엔진 + 다크 팝업 와이어링.

스레드 구조
  - 메인 스레드  : customtkinter mainloop (팝업 소유)
  - 트레이 스레드: pystray icon (데몬)
  - 단축키 콜백  : keyboard 내부 스레드 → 캡처 스레드 spawn
  - 추론 워커    : 엔진 스트림 → 큐 → 메인 스레드 폴링
"""
from __future__ import annotations

import os
import sys
import threading
import ctypes

# ---- 단일 인스턴스 보장 (Windows 네임드 뮤텍스) -------------------------
# run.bat 을 실수로 두 번 실행해도 두 번째는 즉시 종료된다.
_MUTEX_HANDLE = None


def ensure_single_instance() -> None:
    global _MUTEX_HANDLE
    try:
        import win32event
        import win32api
        import winerror
    except Exception:  # noqa: BLE001 (pywin32 없으면 가드 생략)
        return

    _MUTEX_HANDLE = win32event.CreateMutex(None, False, "ClipAI_SingleInstance_Mutex")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            0,
            "ClipAI 가 이미 실행 중입니다.\n트레이 아이콘을 확인하세요.",
            "ClipAI",
            0x40,  # MB_ICONINFORMATION
        )
        sys.exit(0)

# tomllib(3.11+) / tomli(<3.11) 호환
try:
    import tomllib  # type: ignore
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

# src/ 를 import 경로에 추가 (어디서 실행하든 동작)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine as engine_mod
import clipboard
import prompts
from hotkeys import HotkeyManager
from popup import Popup
from tray import Tray


def _app_dir() -> str:
    """config.toml 등 사용자 편집 파일을 두는 폴더.
    - 빌드된 exe: 실행 파일이 있는 폴더 (사용자가 직접 수정 가능)
    - 스크립트 실행: 프로젝트 루트 (src 의 상위)
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_path() -> str:
    return os.path.join(_app_dir(), "config.toml")


def load_config() -> dict:
    path = _config_path()
    with open(path, "rb") as f:
        return tomllib.load(f)


def resolve_model_path(p: str) -> str:
    """모델 경로를 앱 폴더 기준으로 해석하고, 없으면 models/ 의 .gguf 자동 탐색."""
    import glob

    base = _app_dir()
    if p and not os.path.isabs(p):
        p = os.path.join(base, p)
    if p and os.path.exists(p):
        return p
    # 자동 탐색: models/*.gguf 중 가장 큰 파일(보통 본 모델)
    candidates = glob.glob(os.path.join(base, "models", "*.gguf"))
    if candidates:
        candidates.sort(key=lambda f: os.path.getsize(f), reverse=True)
        return candidates[0]
    return p  # 못 찾으면 원래 경로 반환 → 엔진에서 안내 에러


class App:
    def __init__(self):
        self.cfg = load_config()
        model_cfg = dict(self.cfg.get("model", {}))
        if model_cfg.get("backend", "llamacpp") == "llamacpp":
            model_cfg["path"] = resolve_model_path(model_cfg.get("path", ""))
        self.engine = engine_mod.create_engine(model_cfg)
        self.popup = Popup(self.cfg.get("ui", {}))

        # 모드 (config.toml 의 [[modes]] → key 로 인덱싱)
        self.modes = {m["key"]: m for m in prompts.load_modes(self.cfg)}
        if not self.modes:
            raise ValueError("사용 가능한 모드가 없습니다. config.toml 의 [[modes]] 를 확인하세요.")

        # 모델 워밍업 (백그라운드)
        threading.Thread(target=self.engine.warmup, daemon=True).start()

        # 단축키 (모드별 hotkey 매핑)
        mapping = {key: m["hotkey"] for key, m in self.modes.items()}
        self.hotkeys = HotkeyManager(mapping, self._on_hotkey)
        self.hotkeys.register()

        # 트레이
        self.tray = Tray(self.engine.name, on_quit=self._quit, on_rewarm=self._rewarm)
        self.tray.run_detached()

        self._ui_cfg = self.cfg.get("ui", {})
        self._capture_lock = threading.Lock()  # 캡처 중복(연타) 방지

    # ---- 단축키 → 캡처 → 팝업 -------------------------------------------
    def _on_hotkey(self, mode: str):
        # keyboard 콜백 스레드를 막지 않도록 캡처를 별도 스레드로.
        threading.Thread(target=self._handle, args=(mode,), daemon=True).start()

    def _handle(self, mode_key: str):
        mode = self.modes.get(mode_key)
        if mode is None:
            return
        # 이미 캡처가 진행 중이면(연타) 중복 클립보드 조작을 막기 위해 무시
        if not self._capture_lock.acquire(blocking=False):
            return
        try:
            text = clipboard.capture_selection(
                restore=self._ui_cfg.get("restore_clipboard", True),
                timeout_ms=int(self._ui_cfg.get("capture_timeout_ms", 500)),
            )
        finally:
            self._capture_lock.release()
        if not text:
            self.popup.root.after(0, lambda: self.popup.toast(
                "선택된 텍스트가 없습니다.\n텍스트를 드래그한 뒤 다시 시도하세요.\n"
                "(특정 앱에서 안 되면 ClipAI를 관리자 권한으로 실행)"))
            return
        # 메인 스레드에서 팝업 시작
        self.popup.root.after(0, lambda: self.popup.begin(self.engine, mode, text))

    # ---- 트레이 액션 -----------------------------------------------------
    def _rewarm(self):
        threading.Thread(target=self.engine.warmup, daemon=True).start()

    def _quit(self):
        try:
            self.hotkeys.unregister()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.popup.root.after(0, self.popup.root.destroy)
        except Exception:  # noqa: BLE001
            pass

    def run(self):
        print("[ClipAI] 실행 중. 트레이 아이콘에서 종료할 수 있습니다.")
        print(f"[ClipAI] 엔진: {self.engine.name}")
        self.popup.root.mainloop()


def main():
    ensure_single_instance()
    app = App()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # 윈도우 모드(exe)에선 콘솔이 없으므로 크래시를 로그 파일로 남긴다.
        import traceback
        log = os.path.join(_app_dir(), "clipai_error.log")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:  # noqa: BLE001
            pass
        ctypes.windll.user32.MessageBoxW(
            0, f"ClipAI 시작 실패:\n\n{exc}\n\n자세한 내용: {log}", "ClipAI 오류", 0x10
        )
        raise
