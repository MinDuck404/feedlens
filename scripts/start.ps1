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
# "python" trong WindowsApps chỉ là lối tắt mở Microsoft Store, không phải Python thật.
function HasPython($cmd) { $c = Get-Command $cmd -ErrorAction SilentlyContinue; [bool]$c -and $c.Source -notlike "*\WindowsApps\*" }

# ---------------------------------------------------------------- Python
# Máy chưa có Python: tự cài uv (một file nhỏ của Astral), uv sẽ tự tải Python 3.11 riêng cho FeedLens.
function Install-Uv {
    Step "Chưa có Python - đang cài uv để tự lo Python (chỉ lần đầu)…"
    try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }
    catch { Fail "Không tải được uv ($($_.Exception.Message)). Kiểm tra mạng, hoặc cài Python 3.10+ tại https://www.python.org/downloads/ (tick 'Add to PATH')." }
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Has "uv")) { Fail "Cài uv xong nhưng chưa tìm thấy lệnh uv. Mở lại start.bat thử lần nữa." }
}
if (-not (Test-Path $Py)) {
    Step "Tạo môi trường Python (lần đầu)…"
    if (-not (Has "uv") -and -not (HasPython "py") -and -not (HasPython "python")) { Install-Uv }
    if (Has "uv") { uv venv $Venv --python 3.11 -q }
    elseif (HasPython "py") { py -3 -m venv $Venv }
    else { python -m venv $Venv }
    if (-not (Test-Path $Py)) { Fail "Không tạo được môi trường Python." }
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
$NeedBuild = -not (Test-Path $Dist) -or $Newest.LastWriteTime -gt (Get-Item $Dist).LastWriteTime
if ($NeedBuild -and (Test-Path $Dist) -and -not (Has "npm")) {
    # Bản tải từ GitHub Releases đã có giao diện dựng sẵn; không có Node thì dùng luôn bản đó.
    Write-Host "Giao diện dựng sẵn có thể cũ hơn mã nguồn, nhưng máy không có Node.js nên dùng bản dựng sẵn." -ForegroundColor Yellow
    $NeedBuild = $false
}
if ($NeedBuild) {
    if (-not (Has "npm")) { Fail "Cần Node.js để build giao diện. Tải bản FeedLens dựng sẵn ở https://github.com/MinDuck404/feedlens/releases (không cần Node), hoặc cài Node.js LTS tại https://nodejs.org." }
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
