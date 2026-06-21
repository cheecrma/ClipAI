# ClipAI — 클립보드 단축키 AI 어시스턴트

> Windows 상주형 트레이 앱. 드래그로 선택한 텍스트를 단축키 한 번으로
> **요약 / 번역 / 리스트 정리** 하고, 다크 팝업에 결과를 **스트리밍**으로 띄운다.
> **완전 독립 실행** — Ollama·인터넷 불필요, 텍스트는 외부로 나가지 않고 전부 로컬(온디바이스) 처리.

이 문서는 "**무엇을 어떻게 만들었는가**"를 정리한 개발/배포 문서입니다.
(원본 설계 명세는 [CLAUDE.md](CLAUDE.md), 최종 사용자용 안내는 [dist/ClipAI/README.md](dist/ClipAI/README.md))

---

## 1. 주요 기능

| 단축키 | 모드 | 동작 |
|---|---|---|
| `Ctrl + Alt + A` | summarize | 선택 텍스트 요약 (원문 언어로) |
| `Ctrl + Alt + S` | listify | 핵심을 불릿 리스트로 정리 |
| `Ctrl + Alt + D` | translate | 한↔영 자동 감지 번역 |

- 다크 테마, **카톡처럼 좁고 긴** 미니 팝업이 마우스 커서 근처에 출현.
- 결과를 **토큰 스트리밍**으로 실시간 표시 (첫 글자까지 ~1.5초).
- `[복사]` 버튼 / `Ctrl+C` 로 결과 복사, `Esc`/`[닫기]` 로 닫기.
- 팝업 **헤더 드래그로 이동**, **상하좌우 변/모서리 드래그로 크기 조절**.
- 트레이에서 **윈도우 시작 시 자동 실행** 토글.

---

## 2. 사용 모델

- **EXAONE 3.5 2.4B Instruct** (LG AI Research), `Q4_K_M` 양자화, **GGUF** 포맷.
  - 파일: `models/EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf` (약 1.6GB)
  - 한·영 이중언어 특화 → 크기 대비 한국어 요약/번역 품질이 우수.
  - 요약·번역·리스트 같은 "즉답형" 작업엔 거대 모델의 추론력이 불필요 → **2.4B가 속도·품질·용량 균형점**.
- **모델 교체 가능**: `models/` 폴더에 다른 `.gguf` 를 넣으면 됨.
  자세한 안내는 [models/MODEL_GUIDE.md](models/MODEL_GUIDE.md).
- **GGUF** = llama.cpp 용 단일 파일 모델 포맷 (가중치 + 토크나이저 + 채팅 템플릿 + 메타데이터).
  `Q4_K_M` 은 품질 손실이 거의 없는 표준 양자화 수준(원본 fp16 ~4.8GB → ~1.6GB).

---

## 3. 기술 스택 / 설치한 라이브러리

Python **3.9.9** 기준. (`pip install -r requirements.txt`)

| 라이브러리 | 버전 | 용도 |
|---|---|---|
| `llama-cpp-python` | **0.3.2** | 인프로세스 LLM 추론(스트리밍). **CPU(AVX2) 휠** |
| `customtkinter` | 5.2.2 | 다크 테마 팝업 UI |
| `pystray` | 0.19.5 | 트레이 아이콘/메뉴 |
| `Pillow` | 11.1.0 | 아이콘 이미지 생성 |
| `keyboard` | 0.13.5 | 전역 단축키 + Ctrl+C 시뮬레이션 |
| `pyperclip` | 1.11.0 | 클립보드 읽기/쓰기 |
| `pywin32` | 312 | 단일 인스턴스(뮤텍스), 트레이 백엔드 |
| `requests` | 2.32.5 | Ollama 백엔드(개발용) HTTP |
| `tomli` | 2.4.1 | `config.toml` 파싱 (Py<3.11 용) |
| `pyinstaller` | 6.19.0 | `.exe` 패키징 (빌드 전용) |

> 의존 설치: `numpy 2.0.2`, `diskcache 5.6.3`, `jinja2 3.0.3`(llama_cpp 채팅 템플릿).

`llama-cpp-python` 설치 명령 (AVX2 CPU 휠):
```bash
pip install "llama-cpp-python==0.3.2" --only-binary=:all: \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

---

## 4. 프로젝트 구조

```
DanChucKic/
├── CLAUDE.md                 # 원본 설계 명세
├── README.md                 # (이 문서) 개발/배포 정리
├── config.toml               # 설정 (모델/단축키/UI/성능)
├── requirements.txt
├── run.bat                   # 개발 실행
├── clipai.ico                # 트레이/exe 아이콘
├── src/
│   ├── main.py               # 진입점: 단일인스턴스 + 엔진 + 단축키 + 트레이 + UI 와이어링
│   ├── engine.py             # LLM 백엔드 (LlamaCpp / Ollama), 스트리밍, 입력 길이 맞춤(fit_input)
│   ├── prompts.py            # 모드별 시스템 프롬프트 + 언어 감지 + 샘플링 파라미터
│   ├── clipboard.py          # 선택 캡처(Ctrl+C 시뮬 + 센티넬 폴링), 백업/복원
│   ├── popup.py              # 다크 팝업(재사용, 스트리밍 렌더, 변 드래그 리사이즈)
│   ├── hotkeys.py            # 전역 단축키 등록/해제
│   ├── tray.py               # 트레이 아이콘/메뉴(자동실행 토글, 재워밍, 종료)
│   ├── autostart.py          # 윈도우 시작 시 자동 실행 (HKCU Run 레지스트리)
│   └── workers.py            # 추론 스레드 → 큐 (UI 마샬링)
├── models/
│   ├── EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf
│   └── MODEL_GUIDE.md
├── build/
│   ├── clipai.spec           # PyInstaller 스펙 (onedir)
│   └── make_icon.py          # 아이콘 생성 스크립트
└── dist/
    ├── ClipAI/               # 빌드 결과 (실행 폴더)
    └── ClipAI-standalone-win64.zip   # 배포용 zip (~1.6GB)
```

---

## 5. 아키텍처 / 동작 흐름

### 스레드 모델
- **메인 스레드**: customtkinter mainloop (팝업 소유, 모든 tk 조작)
- **트레이 스레드**: pystray 아이콘 (데몬)
- **단축키 콜백**: `keyboard` 내부 스레드 → 캡처 스레드 spawn (리스너 안 막음)
- **추론 워커**: 엔진 스트림 → `queue` → 메인 스레드가 `after`로 폴링하며 팝업에 append

### 단축키 → 결과
1. 단축키 감지 → 캡처 스레드 시작
2. 모디파이어 해제 후 **센티넬 기법**으로 선택 텍스트 캡처
   (클립보드를 고유값으로 덮고 Ctrl+C → 값이 바뀌면 그게 선택 텍스트. 스테일 값 방지)
3. 원래 클립보드 복원 (기본 ON)
4. 메인 스레드에서 팝업 show (커서 근처) + 경과시간 타이머 시작
5. 입력이 컨텍스트를 넘으면 토크나이저로 정확히 잘라냄(`fit_input`) → "긴 글 일부만" 표시
6. 워커가 토큰 스트리밍 → 큐 → 팝업 실시간 렌더
7. 완료 시 타이머 정지, `[복사]` 활성화

### 레이턴시 대응 (CLAUDE.md §8 충족)
모델 시작 시 1회 로드 후 상주 · 팝업 미리 생성 후 show/hide 재사용 ·
토큰 스트리밍 · mmap 로딩 · 자동 멀티스레드 · 머리말 억제 프롬프트 · 워밍업.

---

## 6. 주요 설계 결정 / 고려사항

가장 중요한 의사결정과 그 이유입니다.

### 6.1 추론 백엔드: Ollama(프로토타입) → llama-cpp-python(배포)
- 초기엔 이미 설치된 **Ollama**로 빠르게 프로토타입 (`keep_alive:-1` + 스트리밍).
- 최종 목표인 "Ollama 불필요 단독 exe"를 위해 **llama-cpp-python 인프로세스**로 전환.
- `engine.py` 가 두 백엔드를 모두 지원 → `config.toml` 의 `backend` 로 전환.

### 6.2 CPU 빌드 + `llama-cpp-python==0.3.2` 고정 (★ 중요)
- 배포 대상이 **NVIDIA 없는 환경(LG그램 등)** 이라 **CPU 빌드**로 통일 (어디서든 동작).
- 최신 `0.3.30` CPU 휠은 **AVX512** 명령을 써서 12세대 인텔(i5-12400F, AVX512 미지원)·
  LG그램에서 즉시 크래시(`0xc000001d` ILLEGAL_INSTRUCTION).
  → **AVX2 기반 0.3.2 로 고정**해 광범위 CPU 호환 확보.
- `n_gpu_layers = 0`. (NVIDIA GPU에서 가속하려면 별도 CUDA 빌드 필요 — 미적용)

### 6.3 단축키: `Ctrl+Alt+A/S/D`
- `Ctrl+글자`(워드 단축키 충돌)·`Alt+글자`(메뉴 니모닉)·`Ctrl+Shift+T`(브라우저 탭복원) 등은
  **어느 앱과든 충돌**. 워드/메모장/브라우저 모두 안전한 영역은 **`Ctrl+Alt`(AltGr)** 뿐.
- 손이 편하도록 **왼손 홈row A·S·D** 로 배치.

### 6.4 팝업 UX
- 테두리 없는(overrideredirect) **사각 모서리** (투명 코너 처리 시 생기던 잔상 제거).
- **카톡형 좁고 긴** 기본 크기(340×580). overrideredirect라 OS 리사이즈가 없어
  **4변 + 4모서리에 핸들**을 직접 구현해 드래그 리사이즈 지원.
- 포커스 아웃 자동 닫힘은 "의도치 않게 닫힌다"는 이유로 **비활성**(Esc/닫기만).

### 6.5 안정성 / 편의
- **단일 인스턴스**: 네임드 뮤텍스로 중복 실행 차단 (run.bat 두 번 눌러도 안전).
- **모델 자동 탐색**: `config.toml` 의 `path` 가 없으면 `models/*.gguf` 중 가장 큰 파일 사용
  → 사용자가 `.gguf` 만 넣어도 인식.
- **긴 입력 안전 처리**: 컨텍스트 초과 시 토크나이저로 정확히 앞부분만 남김 → 크래시/잘림 방지.
- **크래시 로깅**: 윈도우 모드(콘솔 없음)에서 시작 실패 시 `clipai_error.log` 기록 + 안내창.

### 6.6 패키징 (PyInstaller onedir)
- **onedir** 채택(onefile은 매 실행 임시 추출로 상주앱에 불리).
- 모델 GGUF는 exe에 안 넣고 **`models/` 외부 배치** → 교체 가능 + exe 경량.
- **공유 파이썬 환경에 깔린 무거운 패키지(torch+CUDA ~2GB, OpenCV 등)가 transitively 끌려와**
  빌드가 4GB+로 부풀던 문제 → spec `excludes` 로 제외 → `_internal` **4,223MB → 133MB**.
- `llama_cpp` 의 `llama.dll`/`ggml*.dll` 은 `collect_dynamic_libs` 로 번들.

---

## 7. 설정 (config.toml)

```toml
[model]
backend   = "llamacpp"   # "llamacpp"(독립) | "ollama"(개발) | "remote"(확장)
path      = "models/EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf"  # 없으면 models/*.gguf 자동
n_ctx     = 4096         # 입력 최대 길이(모델 최대 32768). ↑면 긴글 가능/RAM↑
n_gpu_layers = 0         # CPU 빌드는 0
n_threads = 0            # 0=자동(전체 코어)
n_batch   = 1024         # 입력 ingest 배치(기본 512). ↑면 긴글 읽기 빠름

[hotkeys]
summarize = "ctrl+alt+a"
listify   = "ctrl+alt+s"
translate = "ctrl+alt+d"

[ui]
width  = 340             # 카톡형 좁은 폭
height = 580             # 긴 세로
restore_clipboard = true
capture_timeout_ms = 350
hide_on_focus_loss = false
```

---

## 7-1. GitHub 로 옮겨 쓰기 (회사 PC 등)

> 모델(`.gguf`, 1.6GB)은 GitHub 100MB 제한 때문에 **git에 포함하지 않는다.**
> 코드와 **빌드된 exe(`dist/ClipAI/`)는 포함**되어 있어, 회사 PC에선 모델만 받으면 바로 실행된다.

**처음 한 번 (회사 PC):**
```powershell
git clone <repo-URL>
cd DanChucKic
# 모델 받기 (둘 중 하나)
powershell -ExecutionPolicy Bypass -File get-model.ps1   # HuggingFace 에서 자동 다운로드
#  또는 회사망이 막혀 있으면 집에서 받은 .gguf 를 USB로 dist\ClipAI\models\ 에 복사
dist\ClipAI\ClipAI.exe   # 더블클릭 실행 (Python 불필요)
```

**이후 업데이트:** `git pull` 만 하면 코드·exe 최신화. 모델은 그대로 두면 됨.

> 회사망이 HuggingFace 를 차단하면 `get-model.ps1` 이 실패한다. 그땐 집에서 받은
> `models/EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf` 를 **USB로 한 번** 옮기면 끝.

---

## 8. 빌드 / 실행

```bash
# 개발 실행
python src/main.py          # 또는 run.bat

# exe 빌드 (프로젝트 루트에서)
pyinstaller build/clipai.spec --noconfirm --clean --distpath dist --workpath build/_work
# 빌드 후 config.toml 과 models/ 를 dist/ClipAI/ 옆에 배치
```

배포는 `dist/ClipAI/` 폴더를 zip으로 묶어 전달 → 받는 PC에서 풀고 `ClipAI.exe` 실행.

---

## 9. 성능 (i5-12400F, CPU)

| 항목 | 수치 |
|---|---|
| 모델 로드 | ~0.5초 (mmap) |
| 첫 토큰 | ~1.5초 |
| 요약 완료 | ~3.5초 |
| 빌드 용량 | exe 폴더 ~133MB + 모델 1.6GB, zip ~1.6GB |

목표였던 "10초 이내"를 GPU 없이도 충족.

---

## 10. 향후 확장 (현재 범위 밖)

- **데스크톱 전용 CUDA 빌드**(RTX 2060 등 NVIDIA) → 더 빠른 추론 (NVIDIA 전용 별도 빌드).
- **인텔 내장GPU(Vulkan/SYCL) 빌드** → 소스 컴파일 필요, 이득 제한적.
- 모드 추가(말투 교정/코드 설명 등), 결과 히스토리, 설정 GUI, 원격(`backend="remote"`) 엔드포인트.
