@echo off
rem FeedLens - bấm đúp file này để chạy (Windows)
rem Browser warnings are handled by scripts/start.ps1; startup continues without installing a browser.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
