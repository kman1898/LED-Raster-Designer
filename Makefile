# LED Raster Designer - Build System
# 
# macOS:   Open Terminal, cd to this folder, type: make install-mac
# Windows: Open Command Prompt, cd to this folder, type: make install-pc

.PHONY: deps install-mac install-pc clean

deps:
	cd src && python3 -m pip install -r requirements.txt
	python3 -m pip install pyinstaller

install-mac: deps
	python3 -m pip install rumps
	@echo "============================================================"
	@echo "Building LED Raster Designer for macOS..."
	@echo "============================================================"
	cd src && python3 -m PyInstaller led_raster_designer.spec --noconfirm
	@echo ""
	@echo "Moving app to main folder..."
	cp -R "src/dist/LED Raster Designer.app" "./LED Raster Designer.app"
	@echo ""
	@echo "============================================================"
	@echo "DONE! Double-click LED Raster Designer.app to launch."
	@echo "============================================================"

install-pc: deps
	python3 -m pip install pystray
	@echo ============================================================
	@echo Building LED Raster Designer for Windows...
	@echo ============================================================
	cd src && python3 -m PyInstaller led_raster_designer.spec --noconfirm
	@echo.
	@echo Moving app to main folder...
	xcopy /E /I /Y "src\dist\LED Raster Designer" ".\LED Raster Designer App"
	@echo.
	@echo ============================================================
	@echo DONE! Double-click LED Raster Designer.exe to launch.
	@echo ============================================================

clean:
	rm -rf src/build src/dist src/__pycache__
	rm -rf "LED Raster Designer.app" "LED Raster Designer App"
	rm -f *.zip
