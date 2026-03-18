@echo off
:: ==========================================
:: FloatDesk Remind - Run Tests
:: ==========================================
cd /d "%~dp0.."
python -m pytest tests\ -v --tb=short
