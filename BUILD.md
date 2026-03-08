# How to Build LED Raster Designer

## macOS

1. Open **Terminal**
2. `cd` into the **LED Raster Designer** folder:
   ```
   cd "/path/to/LED Raster Designer"
   ```
3. Type:
   ```
   make install-mac
   ```
4. When it finishes you get:
   - **LED Raster Designer.app** in the `dist/` folder — double-click to launch
   - **Mac LED Raster Designer Installer.zip** — upload this to GitHub Releases

## Windows

1. Open **Command Prompt**
2. `cd` into the **LED Raster Designer** folder:
   ```
   cd "C:\path\to\LED Raster Designer"
   ```
3. If you have `make` installed:
   ```
   make install-pc
   ```
   Otherwise run these commands manually:
   ```
   pip install -r requirements.txt
   pip install pyinstaller
   pyinstaller led_raster_designer.spec --noconfirm
   ```
4. When it finishes you get:
   - **LED Raster Designer.exe** in `dist\LED Raster Designer\` — double-click to launch
   - **PC LED Raster Designer Installer.zip** — upload this to GitHub Releases

## Prerequisites

- Python 3.10+ (https://python.org/downloads)
- Windows users: CHECK "Add Python to PATH" during install

## What Users Get

When someone downloads the installer zip from GitHub:
- **Mac**: Unzip → double-click **LED Raster Designer.app** → browser opens automatically
- **PC**: Unzip → double-click **LED Raster Designer.exe** → browser opens automatically
