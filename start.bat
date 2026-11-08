@echo off
rem Film Oneri - tek tikla baslat. Frontend build yoksa once build alir.
cd /d "%~dp0"

if not exist "frontend\dist\index.html" (
    echo Frontend build aliniyor...
    pushd frontend
    if not exist "node_modules" call npm install
    call npm run build
    popd
)

rem Sunucu ayaga kalkinca tarayiciyi ac.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

uv run film serve
pause
