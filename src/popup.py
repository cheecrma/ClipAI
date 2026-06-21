"""다크 테마 미니 팝업 (재사용형).

- 윈도우 1개를 hide/show 로 재사용 (파괴하지 않음).
- 마우스 커서 근처에 출현, always-on-top, 사각 모서리.
- 좁고 긴(카톡 느낌) 기본 크기 + 상하좌우 변 드래그로 리사이즈.
- 헤더: 모드 아이콘+이름 / 우측 경과시간 실시간 갱신.
- 본문: 스트리밍 토큰 실시간 append.
- 푸터: [복사] [닫기] + 단축키 힌트.
- Esc 닫기, 포커스 아웃 시 hide.

스레드 모델: 모든 tk 조작은 메인 스레드에서. 워커→UI 전달은 queue + after 폴링.
"""
from __future__ import annotations

import queue
import time
import tkinter as tk

import customtkinter as ctk

from workers import run_stream
import prompts
import clipboard

# 색상 팔레트 (다크)
_BG = "#1c1c20"
_HEADER_BG = "#26262c"
_BODY_BG = "#1c1c20"
_TEXT = "#ececf0"
_MUTED = "#8a8a95"
_ACCENT = "#6c8cff"
_BTN = "#33333c"
_BTN_HOVER = "#41414c"
_BORDER = "#3a3a44"

_EDGE = 6        # 가장자리 리사이즈 감지 두께(px)
_MIN_W = 260     # 최소 폭
_MIN_H = 260     # 최소 높이 (푸터까지 항상 보이도록)


class Popup:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        # 카톡 느낌: 좁은 폭 + 긴 세로
        self.width = int(cfg.get("width", 340))
        self.height = int(cfg.get("height", 580))
        ctk.set_appearance_mode("dark")

        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=_BG)

        # 바깥 프레임 (사각 모서리, 얇은 테두리)
        self.card = ctk.CTkFrame(
            self.root, corner_radius=0, fg_color=_BG,
            border_width=1, border_color=_BORDER,
        )
        self.card.pack(fill="both", expand=True)

        self._build_header()
        self._build_body()
        self._build_footer()
        self._build_resize_edges()

        # 상태
        self.queue: "queue.Queue" = queue.Queue()
        self.gen = 0
        self.running = False
        self.start_ts = 0.0
        self._result_text = ""
        self._shown_at = 0.0  # 마지막으로 팝업을 띄운 시각(포커스아웃 유예용)
        self._sized = False   # 최초 표시 때 기본(카톡) 크기 강제, 이후엔 사용자 크기 유지

        # 바인딩
        self.root.bind("<Escape>", lambda e: self.hide())
        self.root.bind("<Control-c>", lambda e: self.copy())
        # 포커스 아웃(팝업 밖 클릭) 시 자동 닫힘
        self._hide_on_focus_loss = bool(cfg.get("hide_on_focus_loss", False))
        if self._hide_on_focus_loss:
            self.root.bind("<FocusOut>", self._on_focus_out)
        # 헤더 드래그로 이동
        for w in (self.header, self.mode_lbl):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

    # ---- UI 구성 ----------------------------------------------------------
    def _build_header(self):
        self.header = ctk.CTkFrame(self.card, fg_color=_HEADER_BG, corner_radius=12, height=40)
        self.header.pack(fill="x", padx=10, pady=(10, 6))
        self.header.pack_propagate(False)

        self.mode_lbl = ctk.CTkLabel(
            self.header, text="ClipAI", text_color=_TEXT,
            font=("Malgun Gothic", 14, "bold"), anchor="w",
        )
        self.mode_lbl.pack(side="left", padx=12)

        self.timer_lbl = ctk.CTkLabel(
            self.header, text="0.0s", text_color=_MUTED,
            font=("Consolas", 12), anchor="e",
        )
        self.timer_lbl.pack(side="right", padx=12)

        self.spinner_lbl = ctk.CTkLabel(
            self.header, text="", text_color=_ACCENT,
            font=("Consolas", 12),
        )
        self.spinner_lbl.pack(side="right")

    def _build_body(self):
        self.body = ctk.CTkTextbox(
            self.card, fg_color=_BODY_BG, text_color=_TEXT,
            corner_radius=10, wrap="word", border_spacing=10,
            font=("Malgun Gothic", 14), width=self.width - 20, height=120,
            scrollbar_button_color=_BTN, scrollbar_button_hover_color=_BTN_HOVER,
        )
        self.body.pack(fill="both", expand=True, padx=10, pady=2)
        self.body.configure(state="disabled")

    def _build_footer(self):
        self.footer = ctk.CTkFrame(self.card, fg_color="transparent", height=44)
        self.footer.pack(fill="x", padx=10, pady=(6, 10))
        self.footer.pack_propagate(False)

        self.hint_lbl = ctk.CTkLabel(
            self.footer, text="Esc 닫기 · Ctrl+C 복사", text_color=_MUTED,
            font=("Malgun Gothic", 11), anchor="w",
        )
        self.hint_lbl.pack(side="left", padx=6)

        self.close_btn = ctk.CTkButton(
            self.footer, text="닫기", width=72, height=30, corner_radius=8,
            fg_color=_BTN, hover_color=_BTN_HOVER, text_color=_TEXT,
            command=self.hide,
        )
        self.close_btn.pack(side="right", padx=(6, 0))

        self.copy_btn = ctk.CTkButton(
            self.footer, text="복사", width=80, height=30, corner_radius=8,
            fg_color=_ACCENT, hover_color="#5577ee", text_color="#ffffff",
            command=self.copy,
        )
        self.copy_btn.pack(side="right")

    # ---- 가장자리 리사이즈 (상하좌우 변 드래그) --------------------------
    def _build_resize_edges(self):
        """창 4개 변에 얇은 핸들을 얹어 마우스로 크기 조절. overrideredirect 라
        OS 기본 리사이즈가 없으므로 직접 구현."""
        specs = [
            ("top",    {"relx": 0, "rely": 0, "relwidth": 1, "height": _EDGE}, "sb_v_double_arrow"),
            ("bottom", {"relx": 0, "rely": 1.0, "relwidth": 1, "height": _EDGE, "anchor": "sw"}, "sb_v_double_arrow"),
            ("left",   {"relx": 0, "rely": 0, "relheight": 1, "width": _EDGE}, "sb_h_double_arrow"),
            ("right",  {"relx": 1.0, "rely": 0, "relheight": 1, "width": _EDGE, "anchor": "ne"}, "sb_h_double_arrow"),
            ("topleft",     {"relx": 0, "rely": 0, "width": _EDGE * 2, "height": _EDGE * 2}, "size_nw_se"),
            ("topright",    {"relx": 1.0, "rely": 0, "width": _EDGE * 2, "height": _EDGE * 2, "anchor": "ne"}, "size_ne_sw"),
            ("bottomleft",  {"relx": 0, "rely": 1.0, "width": _EDGE * 2, "height": _EDGE * 2, "anchor": "sw"}, "size_ne_sw"),
            ("bottomright", {"relx": 1.0, "rely": 1.0, "width": _EDGE * 2, "height": _EDGE * 2, "anchor": "se"}, "size_nw_se"),
        ]
        for side, place_kw, cursor in specs:
            f = tk.Frame(self.root, bg=_BG, cursor=cursor)
            f.place(**place_kw)
            f.bind("<Button-1>", lambda e, s=side: self._edge_start(e, s))
            f.bind("<B1-Motion>", lambda e, s=side: self._edge_move(e, s))

    def _edge_start(self, event, side):
        self._rx, self._ry = event.x_root, event.y_root
        self._rw, self._rh = self.root.winfo_width(), self.root.winfo_height()
        self._rox, self._roy = self.root.winfo_x(), self.root.winfo_y()

    def _edge_move(self, event, side):
        dx = event.x_root - self._rx
        dy = event.y_root - self._ry
        x, y, w, h = self._rox, self._roy, self._rw, self._rh
        if "right" in side:
            w = max(_MIN_W, self._rw + dx)
        if "left" in side:
            w = max(_MIN_W, self._rw - dx)
            x = self._rox + (self._rw - w)
        if "bottom" in side:
            h = max(_MIN_H, self._rh + dy)
        if "top" in side:
            h = max(_MIN_H, self._rh - dy)
            y = self._roy + (self._rh - h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ---- 위치 / 표시 ------------------------------------------------------
    def _place_near_cursor(self):
        """카톡 느낌의 좁고 긴 창을 커서 근처에 띄운다. (크기는 유지)"""
        self.root.update_idletasks()
        px, py = self.root.winfo_pointerxy()
        if not self._sized:                    # 최초 표시: 카톡 기본 크기 강제
            w, h = self.width, self.height
            self._sized = True
        else:                                  # 이후: 사용자가 조절한 크기 유지
            w = self.root.winfo_width()
            h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = min(max(px + 16, 8), sw - w - 8)
        y = min(max(py + 16, 8), sh - h - 8)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def hide(self):
        self.running = False
        self.root.withdraw()

    def _on_focus_out(self, _event=None):
        # 잠시 뒤 포커스가 앱 밖으로 나갔는지 확인 후 숨김
        # (팝업 내부 위젯 간 이동은 무시)
        self.root.after(120, self._maybe_hide)

    def _maybe_hide(self):
        try:
            if self.root.state() == "withdrawn":
                return
            # 막 떠서 포커스가 잡히기 전이면(0.6s 유예) 닫지 않음
            if time.time() - self._shown_at < 0.6:
                return
            if self.root.focus_get() is None:  # 다른 앱이 포커스를 가져감
                self.hide()
        except Exception:  # noqa: BLE001
            pass

    # ---- 본문 조작 --------------------------------------------------------
    def _set_body(self, text: str):
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", text)
        self.body.configure(state="disabled")

    def _append_body(self, text: str):
        self.body.configure(state="normal")
        self.body.insert("end", text)
        self.body.see("end")
        self.body.configure(state="disabled")

    # ---- 동작: 스트리밍 시작 ---------------------------------------------
    def begin(self, engine, mode: str, text: str):
        """단축키 트리거 시 호출 (메인 스레드)."""
        meta = prompts.MODES.get(mode, {"icon": "✨", "title": mode})
        system, user, options, banner = prompts.build(mode, text)

        # 긴 입력은 컨텍스트에 맞게 안전하게 자른다
        try:
            user, truncated = engine.fit_input(system, user, options.get("num_predict", 256))
        except Exception:  # noqa: BLE001
            truncated = False
        if truncated:
            banner = (banner + "  · " if banner else "") + "긴 글 일부만"

        header_text = f"{meta['icon']}  {meta['title']}"
        if banner:
            header_text += f"   ({banner})"
        self.mode_lbl.configure(text=header_text)

        self._result_text = ""
        self._set_body("")
        self.copy_btn.configure(state="disabled", text="복사")
        self._place_near_cursor()
        self._shown_at = time.time()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        try:
            self.root.focus_force()
        except Exception:  # noqa: BLE001
            pass

        self.gen += 1
        gen = self.gen
        self.running = True
        self.start_ts = time.time()

        run_stream(engine, system, user, options, self.queue, gen)
        self._tick_timer(gen)
        self._poll_queue(gen)

    # ---- 타이머 / 큐 폴링 -------------------------------------------------
    def _tick_timer(self, gen):
        if gen != self.gen:
            return
        elapsed = time.time() - self.start_ts
        self.timer_lbl.configure(text=f"{elapsed:0.1f}s")
        if self.running:
            # 간단한 스피너 애니메이션
            frame = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(elapsed * 10) % 10]
            self.spinner_lbl.configure(text=frame)
            self.root.after(100, lambda: self._tick_timer(gen))
        else:
            self.spinner_lbl.configure(text="")

    def _poll_queue(self, gen):
        if gen != self.gen:
            return
        try:
            while True:
                g, kind, payload = self.queue.get_nowait()
                if g != self.gen:
                    continue
                if kind == "token":
                    self._result_text += payload
                    self._append_body(payload)
                elif kind == "done":
                    self._finish()
                    return
                elif kind == "error":
                    self._set_body(f"⚠ 오류: {payload}")
                    self._finish()
                    return
        except queue.Empty:
            pass
        if self.running:
            self.root.after(30, lambda: self._poll_queue(gen))

    def _finish(self):
        self.running = False
        elapsed = time.time() - self.start_ts
        self.timer_lbl.configure(text=f"{elapsed:0.1f}s ✓")
        self.spinner_lbl.configure(text="")
        self.copy_btn.configure(state="normal")
        if not self._result_text.strip():
            self._set_body("(빈 응답)")

    # ---- 토스트 (선택 텍스트 없음 등) ------------------------------------
    def toast(self, message: str):
        self.gen += 1  # 진행 중 스트림 무효화
        self.running = False
        self.mode_lbl.configure(text="ClipAI")
        self.timer_lbl.configure(text="")
        self.spinner_lbl.configure(text="")
        self._result_text = ""
        self._set_body(message)
        self.copy_btn.configure(state="disabled")
        self._place_near_cursor()
        self._shown_at = time.time()
        self.root.deiconify()
        self.root.lift()

    # ---- 복사 -------------------------------------------------------------
    def copy(self):
        if not self._result_text.strip():
            return
        clipboard.set_clipboard(self._result_text.strip())
        self.copy_btn.configure(text="복사됨 ✓")
        self.root.after(1200, lambda: self.copy_btn.configure(text="복사"))

    # ---- 드래그 이동 ------------------------------------------------------
    def _drag_start(self, event):
        self._dx = event.x_root - self.root.winfo_x()
        self._dy = event.y_root - self.root.winfo_y()

    def _drag_move(self, event):
        x = event.x_root - self._dx
        y = event.y_root - self._dy
        self.root.geometry(f"+{x}+{y}")
