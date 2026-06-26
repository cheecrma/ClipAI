"""추론 워커: 엔진 스트림 → 스레드 안전 큐.

UI 스레드는 큐를 폴링해 토큰을 팝업에 append 한다.
큐 메시지: (gen, "token", str) | (gen, "done", None) | (gen, "error", str)
각 작업은 gen(세대 번호)로 태깅 → 이전 요청의 잔여 토큰 무시.

★ 동시 추론 방지 (중요):
llama-cpp-python 의 Llama 는 스레드 안전하지 않다. 추론 중에 새 단축키가
들어와 두 번째 추론이 같은 모델을 동시에 호출하면 네이티브 크래시(exe 종료)가
난다. 그래서:
  - infer_lock : 한 번에 하나의 추론만 실행
  - cancel_event: 새 요청이 들어오면 진행 중 추론에 중단 신호
  - 생성기를 lock 안에서 close() 하여 네이티브 정리도 직렬화
"""
from __future__ import annotations

import threading


def run_stream(engine, system, user, options, out_queue, gen, infer_lock, cancel_event):
    """별도 스레드에서 실행. 토큰을 out_queue 로 흘려보낸다."""
    def _work():
        # 진행 중인 이전 추론에게 "그만" 신호 → 곧 lock 을 놓는다.
        cancel_event.set()
        with infer_lock:
            cancel_event.clear()  # 내 차례
            stream_gen = None
            try:
                stream_gen = engine.stream(system, user, options)
                completed = True
                for piece in stream_gen:
                    if cancel_event.is_set():  # 더 새 요청이 들어옴 → 중단
                        completed = False
                        break
                    out_queue.put((gen, "token", piece))
                if completed:
                    out_queue.put((gen, "done", None))
            except Exception as e:  # noqa: BLE001
                out_queue.put((gen, "error", str(e)))
            finally:
                # lock 을 쥔 채로 생성기를 닫아 네이티브 자원 정리까지 직렬화
                if stream_gen is not None:
                    try:
                        stream_gen.close()
                    except Exception:  # noqa: BLE001
                        pass

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    return t
