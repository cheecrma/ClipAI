"""추론 워커: 엔진 스트림 → 스레드 안전 큐.

UI 스레드는 큐를 폴링해 토큰을 팝업에 append 한다.
큐 메시지: ("token", str) | ("done", None) | ("error", str)
각 작업은 gen(세대 번호)로 태깅 → 이전 요청의 잔여 토큰 무시.
"""
from __future__ import annotations

import threading


def run_stream(engine, system, user, options, out_queue, gen):
    """별도 스레드에서 실행. 토큰을 out_queue 로 흘려보낸다."""
    def _work():
        try:
            for piece in engine.stream(system, user, options):
                out_queue.put((gen, "token", piece))
            out_queue.put((gen, "done", None))
        except Exception as e:  # noqa: BLE001
            out_queue.put((gen, "error", str(e)))

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    return t
