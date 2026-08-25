@echo off
REM ============================================================
REM  Build script for Bambu 3MF Renamer
REM  Includes Windows manifest so drag-and-drop works correctly
REM ============================================================

echo Checking for PyInstaller...
python -m pip show pyinstaller >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
)

REM ── Write a Windows app manifest ────────────────────────────
REM This tells Windows the EXE is "asInvoker" (no elevation needed)
REM and sets the right compatibility flags for drag-and-drop to work.
echo Writing manifest...
(
echo ^<?xml version="1.0" encoding="UTF-8" standalone="yes"?^>
echo ^<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"^>
echo   ^<assemblyIdentity
echo     version="1.0.0.0"
echo     processorArchitecture="amd64"
echo     name="MakeItBambuRenamer"
echo     type="win32"
echo   /^>
echo   ^<trustInfo xmlns="urn:schemas-microsoft-com:asm.v2"^>
echo     ^<security^>
echo       ^<requestedPrivileges^>
echo         ^<requestedExecutionLevel level="asInvoker" uiAccess="false" /^>
echo       ^</requestedPrivileges^>
echo     ^</security^>
echo   ^</trustInfo^>
echo   ^<compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"^>
echo     ^<application^>
echo       ^<supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/^>
echo     ^</application^>
echo   ^</compatibility^>
echo ^</assembly^>
) > MakeItBambuRenamer.manifest

REM Remove existing copy
IF EXIST "dist\MakeItBambuRenamer.exe" (
    del dist\MakeItBambuRenamer.exe
)

echo.
echo Building EXE...

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "MakeItBambuRenamer" ^
    --manifest "MakeItBambuRenamer.manifest" ^
    --clean ^
    --icon="MakeItBambuRenamerIcon.ico" ^
    bambu_renamer.py

echo.
IF EXIST "dist\MakeItBambuRenamer.exe" (
    echo ============================================================
    echo  SUCCESS!
    echo.
    echo  EXE location:   dist\MakeItBambuRenamer.exe
    echo.
    echo  SETUP STEPS:
    echo    1. Copy MakeItBambuRenamer.exe to wherever you want to keep it
    echo    2. Right-click MakeItBambuRenamer.exe, select "Properties"
    echo    3. Click "Unblock" at the bottom if that option appears
    echo    4. Click OK
    echo    5. Now drag any .3mf file onto MakeItBambuRenamer.exe
    echo ============================================================
) ELSE (
    echo BUILD FAILED - check output above for errors.
)

pause
