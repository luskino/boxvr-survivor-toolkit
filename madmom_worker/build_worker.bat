@echo off
cd /d "C:\temp_madmom_test"
"C:\temp_madmom_test\venv310\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --console --name "madmom_worker" --collect-all madmom madmom_worker.py
echo ===BUILD EXIT CODE %ERRORLEVEL%===
