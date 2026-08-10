# LED Raster Designer - Build System
#
# macOS:   Open Terminal, cd to this folder, type: make mac
# Windows: double-click "Build Windows.bat" (this Makefile is macOS only -
#          PYTHON below is a POSIX venv path, so a Windows venv, which puts
#          python.exe in .venv/Scripts, could never have run these targets).

.PHONY: deps mac clean

VENV := .venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip

$(VENV):
	python3 -m venv $(VENV)

deps: $(VENV)
	$(PIP) install -r src/requirements.txt
	$(PIP) install pyinstaller

mac: deps
	# rumps, not pystray: launcher_mac.py imports rumps for the menu bar
	# (src/launcher_mac.py), and release.yml installs rumps for the macOS
	# build. pystray is the WINDOWS tray dependency - installing it here
	# produced a local build with its menu-bar dependency missing.
	$(PIP) install rumps
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

clean:
	rm -rf src/build src/dist src/__pycache__
	rm -rf "LED Raster Designer.app" "LED Raster Designer App"
	rm -rf $(VENV)
	rm -f *.zip
