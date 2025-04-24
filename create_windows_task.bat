@echo off
REM Create a scheduled task for daily test generation

echo Creating scheduled task for daily test generation...

REM Set variables
set TASK_NAME=ZavodDailyTestGeneration
set PYTHON_EXE=%cd%\venv\Scripts\python.exe
set SCRIPT_PATH=%cd%\manage.py
set WORKING_DIR=%cd%

REM Create the task
schtasks /create /tn "%TASK_NAME%" /tr "%PYTHON_EXE% %SCRIPT_PATH% generate_daily_tests" /sc DAILY /st 01:00 /ru SYSTEM /f

echo Task created! Tests will be generated daily at 1:00 AM.
echo To verify, run: schtasks /query /tn "%TASK_NAME%"
echo To delete, run: schtasks /delete /tn "%TASK_NAME%" /f

pause 