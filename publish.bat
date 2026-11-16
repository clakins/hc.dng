@echo off
python build.py
git add -A
git commit -m "update portfolio"
git push
pause
