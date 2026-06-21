@echo off
REM ClipAI 실행 (개발용). 트레이에 상주하며 전역 단축키 대기.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python src\main.py
