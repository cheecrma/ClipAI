# get-model.ps1
# 회사 PC 등에서 git pull 후 모델(.gguf)을 자동으로 받아 배치한다.
# 사용법: 탐색기에서 우클릭 > "PowerShell에서 실행"  또는
#         PowerShell 에서:  powershell -ExecutionPolicy Bypass -File get-model.ps1
$ErrorActionPreference = "Stop"

# 기본 모델: Gemma 2 2B (상업 사용 가능, Gemma 약관). 회사 업무용 OK.
# (한국어 품질을 최우선하는 개인/연구용은 MODEL_GUIDE.md 의 EXAONE 참고)
$url  = "https://huggingface.co/lmstudio-community/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$dest = Join-Path $root "dist\ClipAI\models\gemma-2-2b-it-Q4_K_M.gguf"

New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null

if (Test-Path $dest) {
    Write-Host "이미 모델이 있습니다: $dest"
    exit 0
}

Write-Host "모델 다운로드 중 (~1.6GB, 네트워크에 따라 수 분 소요)..."
Write-Host "  -> $dest"
# curl.exe (Windows 10+ 기본 포함)로 리다이렉트 따라가며 스트리밍 다운로드
curl.exe -L --fail -o $dest $url

if (Test-Path $dest) {
    $mb = [math]::Round((Get-Item $dest).Length / 1MB)
    Write-Host "완료: $mb MB"
    Write-Host "이제 dist\ClipAI\ClipAI.exe 를 실행하세요."
} else {
    Write-Host "다운로드 실패. 회사망이 HuggingFace 를 막는 경우,"
    Write-Host "집에서 받은 .gguf 를 USB로 가져와 dist\ClipAI\models\ 에 넣으세요."
    exit 1
}
