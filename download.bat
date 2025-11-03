@echo off
cd /d "%~dp0"
echo Downloading LinkedIn network CSV...
python download_csv.py
pause

