# LED Raster Designer - Build System
# 
# macOS:   Open Terminal, cd to this folder, type: make mac
# Windows: Open Command Prompt, cd to this folder, type: make windows

.PHONY: deps mac windows clean

VENV := .venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip

$(VENV):
	python3 -m venv $(VENV)

deps: $(VENV)
	$(PIP) install -r src/requirements.txt
	$(PIP) install pyinstaller

mac: deps
	$(PIP) install pystray
	@echo "============================================================"
	@echo "Building LED Raster Designer for macOS..."
	@echo "============================================================"
	cd src && $(CURDIR)/$(PYTHON) -m PyInstaller led_raster_designer.spec --noconfirm
	@echo ""
	@echo "Moving app to main folder..."
	cp -R "src/dist/LED Raster Designer.app" "./LED Raster Designer.app"
	@echo ""
	@echo "============================================================"
	@echo "DONE! Double-click LED Raster Designer.app to launch."
	@echo "============================================================"

windows: deps
	$(PIP) install pystray
	@echo ============================================================
	@echo Building LED Raster Designer for Windows...
	@echo ============================================================
	cd src && $(CURDIR)/$(PYTHON) -m PyInstaller led_raster_designer.spec --noconfirm
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
	rm -rf $(VENV)
	rm -f *.zip
