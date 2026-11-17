@echo off
cd /d "%~dp0"
python build.py
git add -A
git commit -m "update portfolio"
git push
pause
