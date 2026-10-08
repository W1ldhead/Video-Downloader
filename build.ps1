# Сборка одного .exe: dist\Video Downloader.exe
# Запуск из папки проекта: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& .\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm --clean `
    --onefile --windowed `
    --name "Video Downloader" `
    --copy-metadata yt-dlp `
    --collect-all curl_cffi `
    --collect-submodules yt_dlp `
    main.py
if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась" }

Get-Item "dist\Video Downloader.exe" | Select-Object Name, @{n = "МБ"; e = { [math]::Round($_.Length / 1MB, 1) } }
