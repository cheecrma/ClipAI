"""모드별 시스템 프롬프트 + 언어 감지 + 샘플링 파라미터.

각 모드는 (system, user, options) 를 생성한다.
options 는 백엔드 공통 키: temperature, num_predict(max_tokens), stop.
"""
from __future__ import annotations

# ---- 모드 메타 (UI 표시용) -------------------------------------------------
MODES = {
    "summarize": {"icon": "📝", "title": "요약"},
    "translate": {"icon": "🌐", "title": "번역"},
    "listify":   {"icon": "•",  "title": "리스트 정리"},
}

# ---- 시스템 프롬프트 -------------------------------------------------------
_SUMMARIZE_SYS = (
    "너는 한국어 요약 도우미다. 입력 텍스트의 핵심만 3~5문장으로, "
    "군더더기·인사말·머리말 없이 요약하라. '요약:' 같은 접두어를 붙이지 마라. "
    "원문이 영어면 영어로, 한국어면 한국어로 답하라."
)

_TRANSLATE_KO2EN_SYS = (
    "Translate the following Korean text into natural, fluent English. "
    "Output only the translation. Do not add explanations, notes, or labels."
)

_TRANSLATE_EN2KO_SYS = (
    "다음 영어 텍스트를 자연스러운 한국어로 번역하라. "
    "번역문만 출력하고 설명·주석·머리말은 절대 붙이지 마라."
)

_LISTIFY_SYS = (
    "입력 내용을 핵심 항목 불릿 리스트로 정리하라. 각 항목은 한 줄, "
    "중복 제거, 논리적 순서. 마크다운 '- ' 형식만 사용하라. "
    "머리말·맺음말·설명 없이 리스트만 출력하라."
)


def detect_korean(text: str) -> bool:
    """한글 비율이 우세하면 True (→ 영어로 번역 대상)."""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    letters = sum(1 for ch in text if ch.isalpha())
    if letters == 0:
        return False
    return hangul / letters > 0.3


def build(mode: str, text: str):
    """returns (system_prompt, user_prompt, options, banner)
    banner: UI 헤더에 보조 표기할 짧은 문자열(번역 방향 등). 없으면 ""."""
    text = text.strip()
    banner = ""

    if mode == "summarize":
        system = _SUMMARIZE_SYS
        options = {"temperature": 0.2, "num_predict": 256}

    elif mode == "translate":
        if detect_korean(text):
            system = _TRANSLATE_KO2EN_SYS
            banner = "KO → EN"
        else:
            system = _TRANSLATE_EN2KO_SYS
            banner = "EN → KO"
        # 출력 길이는 입력에 비례 (최소 128, 최대 768)
        approx = max(128, min(768, int(len(text) * 1.5)))
        options = {"temperature": 0.3, "num_predict": approx}

    elif mode == "listify":
        system = _LISTIFY_SYS
        options = {"temperature": 0.2, "num_predict": 320}

    else:
        raise ValueError(f"unknown mode: {mode}")

    return system, text, options, banner
