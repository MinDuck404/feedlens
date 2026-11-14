# FeedLens - chạy toàn bộ trên máy bằng một lệnh (Windows).
# Lần đầu: tạo môi trường Python, cài thư viện, build giao diện. Các lần sau: chạy ngay.
# Mở http://127.0.0.1:8765 rồi bấm "Đăng nhập" cạnh Facebook ở cột trái.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Venv = Join-Path $Backend ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"
$Port = if ($env:FEEDLENS_PORT) { $env:FEEDLENS_PORT } else { "8765" }

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "Lỗi: $msg" -ForegroundColor Red; Read-Host "Bấm Enter để đóng"; exit 1 }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# ---------------------------------------------------------------- Python
if (-not (Test-Path $Py)) {
    Step "Tạo môi trường Python (lần đầu)…"
    if (Has "uv") { uv venv $Venv --python 3.11 -q }
    elseif (Has "py") { py -3 -m venv $Venv }
    elseif (Has "python") { python -m venv $Venv }
    else { Fail "Chưa có Python 3.10+. Tải tại https://www.python.org/downloads/ (nhớ tick 'Add to PATH')." }
}
$Marker = Join-Path $Venv ".feedlens-installed"
$Hash = (Get-FileHash (Join-Path $Backend "pyproject.toml")).Hash
if (-not (Test-Path $Marker) -or (Get-Content $Marker) -ne $Hash) {
    Step "Cài thư viện Python…"
    if (Has "uv") { uv pip install -e $Backend -q --python $Py }
    else { & $Py -m pip install -q --upgrade pip; & $Py -m pip install -q -e $Backend }
    if ($LASTEXITCODE -ne 0) { Fail "Cài thư viện Python thất bại." }
    Set-Content $Marker $Hash
}

# ---------------------------------------------------------------- Giao diện (build một lần, build lại khi code đổi)
$Dist = Join-Path $Frontend "dist\index.html"
$Newest = Get-ChildItem (Join-Path $Frontend "src"), (Join-Path $Frontend "index.html"), (Join-Path $Frontend "package.json") -Recurse -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not (Test-Path $Dist) -or $Newest.LastWriteTime -gt (Get-Item $Dist).LastWriteTime) {
    if (-not (Has "npm")) { Fail "Cần Node.js để build giao diện lần đầu. Tải tại https://nodejs.org (bản LTS)." }
    Step "Build giao diện…"
    Push-Location $Frontend
    try {
        if (-not (Test-Path "node_modules")) { npm ci --no-audit --no-fund --loglevel=error }
        $env:VITE_API_URL = ""   # chạy cùng địa chỉ với backend
        npm run build --silent
        if ($LASTEXITCODE -ne 0) { Fail "Build giao diện thất bại." }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------- Chạy
Remove-Item Env:FEEDLENS_MODE -ErrorAction SilentlyContinue   # luôn chạy chế độ local
Step "FeedLens đang chạy tại http://127.0.0.1:$Port  (Ctrl+C để dừng)"
& (Join-Path $Venv "Scripts\feedlens.exe") serve --port $Port --open
