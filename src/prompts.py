"""모드 정의 로딩 + 프롬프트 빌드 + 언어 감지.

모드는 config.toml 의 [[modes]] 에서 읽는다 (코드 수정 없이 커스텀 가능).
config 에 modes 가 없으면 아래 기본값(DEFAULT_MODES)을 사용한다.

각 모드(dict) 필드:
  key, hotkey, icon, title, type("simple"|"translate"),
  system (simple) / system_ko2en, system_en2ko (translate),
  temperature, max_tokens
"""
from __future__ import annotations

# config 에 [[modes]] 가 전혀 없을 때 사용하는 기본 모드.
DEFAULT_MODES = [
    {
        "key": "summarize", "hotkey": "ctrl+alt+a", "icon": "📝", "title": "요약",
        "type": "simple",
        "system": ("너는 한국어 요약 도우미다. 입력 텍스트의 핵심만 3~5문장으로, "
                   "군더더기·인사말·머리말 없이 요약하라. '요약:' 같은 접두어를 붙이지 "
                   "마라. 원문이 영어면 영어로, 한국어면 한국어로 답하라."),
        "temperature": 0.2, "max_tokens": 256,
    },
    {
        "key": "listify", "hotkey": "ctrl+alt+s", "icon": "•", "title": "리스트 정리",
        "type": "simple",
        "system": ("입력 내용을 핵심 항목 불릿 리스트로 정리하라. 각 항목은 한 줄, "
                   "중복 제거, 논리적 순서. 마크다운 '- ' 형식만 사용하라. "
                   "머리말·맺음말·설명 없이 리스트만 출력하라."),
        "temperature": 0.2, "max_tokens": 320,
    },
    {
        "key": "translate", "hotkey": "ctrl+alt+d", "icon": "🌐", "title": "번역",
        "type": "translate",
        "system_ko2en": ("Translate the following Korean text into natural, fluent "
                         "English. Output only the translation. Do not add "
                         "explanations, notes, or labels."),
        "system_en2ko": ("다음 영어 텍스트를 자연스러운 한국어로 번역하라. "
                         "번역문만 출력하고 설명·주석·머리말은 절대 붙이지 마라."),
        "temperature": 0.3, "max_tokens": 768,
    },
]


def load_modes(cfg: dict) -> list:
    """config 전체 dict에서 모드 목록을 반환. 없으면 기본값.
    유효성: key/hotkey 필수, 중복 hotkey/key 는 뒤엣것을 무시."""
    modes = cfg.get("modes") or DEFAULT_MODES
    seen_keys, seen_hotkeys, result = set(), set(), []
    for m in modes:
        key = (m.get("key") or "").strip()
        hotkey = (m.get("hotkey") or "").strip().lower()
        if not key or not hotkey:
            print(f"[prompts] 모드 건너뜀(key/hotkey 누락): {m}")
            continue
        if key in seen_keys or hotkey in seen_hotkeys:
            print(f"[prompts] 모드 건너뜀(중복 key/hotkey): {key} {hotkey}")
            continue
        seen_keys.add(key)
        seen_hotkeys.add(hotkey)
        result.append(m)
    return result


def detect_korean(text: str) -> bool:
    """한글 비율이 우세하면 True (→ 영어로 번역 대상)."""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    letters = sum(1 for ch in text if ch.isalpha())
    if letters == 0:
        return False
    return hangul / letters > 0.3


def build(mode: dict, text: str):
    """returns (system_prompt, user_prompt, options, banner).
    banner: 헤더 보조 표기(번역 방향 등). 없으면 ""."""
    text = text.strip()
    banner = ""
    mtype = mode.get("type", "simple")
    temp = float(mode.get("temperature", 0.2))
    max_tokens = int(mode.get("max_tokens", 256))

    if mtype == "translate":
        if detect_korean(text):
            system = mode.get("system_ko2en", "Translate to natural English. Output only the translation.")
            banner = "KO → EN"
        else:
            system = mode.get("system_en2ko", "다음을 자연스러운 한국어로 번역하라. 번역문만 출력.")
            banner = "EN → KO"
        # 출력 길이는 입력 길이에 비례 (상한은 모드의 max_tokens)
        num_predict = max(128, min(max_tokens, int(len(text) * 1.5)))
    else:
        system = mode.get("system", "입력 내용을 도와줘.")
        num_predict = max_tokens

    options = {"temperature": temp, "num_predict": num_predict}
    return system, text, options, banner
