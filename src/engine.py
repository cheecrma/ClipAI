"""LLM 추론 엔진.

백엔드 추상화:
  - OllamaEngine  : 프로토타입/현재. HTTP 스트리밍, keep_alive=-1 로 모델 상주.
  - LlamaCppEngine: 배포 빌드. 인프로세스, 지연 임포트(미설치 환경 대비).

공통 인터페이스:
  engine.stream(system, user, options) -> generator[str]   # 토큰 조각 yield
  engine.warmup()                                           # 모델 메모리 적재
  engine.name -> str                                        # UI 표시용
"""
from __future__ import annotations

import json
import requests


class OllamaEngine:
    def __init__(self, cfg: dict):
        self.model = cfg.get("ollama_model", "exaone3.5:2.4b")
        self.host = cfg.get("ollama_host", "http://localhost:11434").rstrip("/")
        self.n_ctx = cfg.get("n_ctx", 4096)
        self.name = f"Ollama · {self.model}"

    def fit_input(self, system: str, user: str, num_predict: int):
        """입력이 컨텍스트를 넘으면 앞부분만 남겨 안전하게 자른다.
        (Ollama 토크나이저 직접 접근이 어려워 문자 휴리스틱 사용)
        반환: (잘린_user, 잘렸는지_bool)"""
        budget = self.n_ctx - num_predict - 80
        # 한국어 보수적으로 1토큰 ≈ 1.5자 가정
        max_chars = max(400, int((budget - len(system) / 1.5) * 1.5))
        if len(user) <= max_chars:
            return user, False
        return user[:max_chars], True

    def warmup(self):
        """모델을 메모리에 상주시킨다 (콜드 스타트 제거)."""
        try:
            requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "안녕"}],
                    "stream": False,
                    "keep_alive": -1,
                    "options": {"num_predict": 1},
                },
                timeout=120,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[engine] warmup failed: {e}")

    def stream(self, system: str, user: str, options: dict):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            "keep_alive": -1,
            "options": {
                "temperature": options.get("temperature", 0.2),
                "num_predict": options.get("num_predict", 256),
            },
        }
        with requests.post(
            f"{self.host}/api/chat", json=payload, stream=True, timeout=300
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break


class LlamaCppEngine:
    """독립 실행용 인프로세스 백엔드. llama-cpp-python 필요."""

    def __init__(self, cfg: dict):
        import os
        from llama_cpp import Llama  # 지연 임포트

        path = cfg.get("path", "")
        if not path or not os.path.exists(path):
            raise FileNotFoundError(
                "GGUF 모델 파일을 찾을 수 없습니다.\n"
                "models/ 폴더에 .gguf 모델을 넣어주세요.\n"
                f"(설정 경로: {path or '(미지정)'})"
            )

        n_threads = cfg.get("n_threads", 0)
        if not n_threads:  # 0 또는 None → 자동(물리코어 수)
            n_threads = os.cpu_count() or 4

        self.cfg = cfg
        n_ctx = cfg.get("n_ctx", 4096)
        # n_batch: 프롬프트(입력) ingest 배치 크기. 클수록 긴 입력 읽기가 빠르다.
        # n_ctx 보다 클 필요 없으므로 상한을 n_ctx 로 둔다.
        n_batch = min(cfg.get("n_batch", 512) or 512, n_ctx)
        self.llm = Llama(
            model_path=path,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_gpu_layers=cfg.get("n_gpu_layers", 0),
            n_threads=n_threads,
            verbose=False,
        )
        self.n_ctx = cfg.get("n_ctx", 4096)
        self.name = f"llama.cpp · {os.path.basename(path)}"

    def fit_input(self, system: str, user: str, num_predict: int):
        """토크나이저로 정확히 계산해 컨텍스트 초과 시 앞부분만 남긴다.
        반환: (잘린_user, 잘렸는지_bool)"""
        budget = self.n_ctx - num_predict - 80
        sys_tok = self.llm.tokenize(system.encode("utf-8"), add_bos=False)
        avail = max(64, budget - len(sys_tok))
        utok = self.llm.tokenize(user.encode("utf-8"), add_bos=False)
        if len(utok) <= avail:
            return user, False
        cut = self.llm.detokenize(utok[:avail]).decode("utf-8", errors="ignore")
        return cut, True

    def warmup(self):
        # 생성자에서 이미 로드됨. 짧은 추론으로 캐시 워밍.
        try:
            list(self.stream("너는 도우미다.", "안녕", {"num_predict": 1}))
        except Exception as e:  # noqa: BLE001
            print(f"[engine] warmup failed: {e}")

    def stream(self, system: str, user: str, options: dict):
        # system 프롬프트를 user 메시지에 합쳐 단일 user 턴으로 보낸다.
        # 이유: Gemma 등 일부 모델의 채팅 템플릿은 'system' 역할을 거부한다.
        #       합쳐 보내면 EXAONE/Qwen/Gemma 등 어떤 GGUF 든 호환된다.
        content = f"{system}\n\n{user}" if system else user
        messages = [{"role": "user", "content": content}]
        for chunk in self.llm.create_chat_completion(
            messages=messages,
            temperature=options.get("temperature", 0.2),
            max_tokens=options.get("num_predict", 256),
            stream=True,
        ):
            delta = chunk["choices"][0].get("delta", {})
            piece = delta.get("content")
            if piece:
                yield piece


def create_engine(cfg: dict):
    backend = cfg.get("backend", "ollama").lower()
    if backend == "ollama":
        return OllamaEngine(cfg)
    if backend == "llamacpp":
        return LlamaCppEngine(cfg)
    raise ValueError(f"지원하지 않는 backend: {backend}")
