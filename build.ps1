# Сборка одного .exe: dist\Video Downloader.exe (+ папка dist\licenses)
# Запуск из папки проекта: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ffmpeg и Deno — встраиваются в .exe; если их нет, скачать
if (-not ((Test-Path "vendor\bin\ffmpeg.exe") -and (Test-Path "vendor\bin\deno.exe"))) {
    & .\.venv\Scripts\python.exe tools\get_vendor.py
    if ($LASTEXITCODE -ne 0) { throw "Не удалось скачать ffmpeg и Deno" }
}

& .\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm --clean `
    --onefile --windowed `
    --name "Video Downloader" `
    --copy-metadata yt-dlp `
    --collect-all curl_cffi `
    --collect-all yt_dlp_ejs `
    --collect-submodules yt_dlp `
    --add-binary "vendor\bin\ffmpeg.exe;vendor\bin" `
    --add-binary "vendor\bin\deno.exe;vendor\bin" `
    main.py
if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась" }

# Лицензии встроенных программ — рядом с .exe (нужны, если раздавать программу)
New-Item -ItemType Directory -Force "dist\licenses" | Out-Null
Copy-Item "vendor\licenses\*" "dist\licenses\" -Force

Get-Item "dist\Video Downloader.exe" | Select-Object Name, @{n = "МБ"; e = { [math]::Round($_.Length / 1MB, 1) } }
