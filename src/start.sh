#!/bin/bash
echo "LED Raster Designer - Starting..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed!"
    exit 1
fi
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi
echo "Starting server on http://localhost:8050"
open http://localhost:8050 2>/dev/null || xdg-open http://localhost:8050 2>/dev/null &
python3 app.py
