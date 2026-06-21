# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec (onedir). 프로젝트 루트에서 실행:
#   pyinstaller build/clipai.spec --noconfirm --clean
import os
from PyInstaller.utils.hooks import (
    collect_data_files, collect_submodules, collect_dynamic_libs,
)

ROOT = os.path.dirname(SPECPATH)   # SPECPATH = build/, ROOT = 프로젝트 루트

datas = []
datas += collect_data_files("customtkinter")     # 테마/에셋 json
datas += collect_data_files("llama_cpp")         # llama_cpp 부속 파일

binaries = []
binaries += collect_dynamic_libs("llama_cpp")    # llama.dll / ggml*.dll 등

hiddenimports = []
hiddenimports += collect_submodules("customtkinter")
# llama_cpp 는 collect_submodules 하지 않는다 → 안 쓰는 llama_cpp.server(pydantic/
# fastapi 등) 까지 끌려오는 걸 방지. 핵심 모듈은 import 추적으로 자동 포함된다.
hiddenimports += ["pystray._win32", "PIL._tkinter_finder", "win32timezone"]

a = Analysis(
    [os.path.join(ROOT, "src", "main.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # ClipAI 는 쓰지 않지만 공유 파이썬 환경에 깔려 transitively 끌려오는
    # 무거운 패키지들을 제외 (특히 torch+CUDA, opencv → 수 GB 절감).
    excludes=[
        "torch", "torchvision", "torchaudio",
        "cv2", "opencv-python",
        "transformers", "tokenizers", "sentence_transformers",
        "scipy", "pandas", "matplotlib", "sklearn", "scikit_learn",
        "tensorflow", "sympy", "numba", "onnxruntime", "accelerate",
        "datasets", "chromadb", "langchain", "langchain_core",
        "IPython", "jupyter", "notebook", "nbconvert", "nbformat",
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        # 추가: 공유 환경 잔재 + llama_cpp.server 의존(미사용)
        "django", "selenium", "cryptography",
        "pydantic", "pydantic_core", "fastapi", "starlette", "uvicorn",
        "httpx", "httpcore", "anyio", "sniffio", "sse_starlette",
        "zmq", "pyzmq", "zstandard", "pytz", "sqlalchemy", "yaml",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClipAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # 트레이 상주 앱 → 콘솔 숨김
    icon=os.path.join(ROOT, "clipai.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ClipAI",
)
