@echo off

if "%1"=="clean" (
    echo Cleaning build files...
    if exist "LED Raster Designer App" rmdir /S /Q "LED Raster Designer App"
    if exist "src\build" rmdir /S /Q "src\build"
    if exist "src\dist" rmdir /S /Q "src\dist"
    echo Done.
    pause
    exit /b
)

echo ============================================================
echo LED Raster Designer - Windows Build
echo ============================================================

echo.
echo [1/4] Installing dependencies...
cd src
python -m pip install -r requirements.txt
python -m pip install pyinstaller pystray

echo.
echo [2/4] Building executable...
python -m PyInstaller led_raster_designer.spec --noconfirm

echo.
echo [3/4] Moving app to main folder...
cd ..
if exist "LED Raster Designer App" rmdir /S /Q "LED Raster Designer App"
xcopy /E /I /Y "src\dist\LED Raster Designer" "LED Raster Designer App"

echo.
echo ============================================================
echo [4/4] DONE! Double-click to launch:
echo.
echo   LED Raster Designer App\LED Raster Designer.exe
echo.
echo To clean build files later, run:
echo   "Build Windows.bat" clean
echo ============================================================
pause
