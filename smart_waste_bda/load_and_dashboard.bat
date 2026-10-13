@echo off
REM load_and_dashboard.bat
REM Loads the latest results into MongoDB, then launches the dashboard.
REM Run this AFTER run_pipeline.sh has finished inside WSL.
REM
REM Double-click this file, or run it from Command Prompt:
REM     load_and_dashboard.bat

cd /d "%~dp0"

echo ====================================================
echo  STEP 1: Loading results into MongoDB
echo ====================================================
python mongo_loader.py
if errorlevel 1 (
    echo.
    echo Mongo loading failed. Fix the error above before continuing.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo  STEP 2: Launching the Streamlit dashboard
echo ====================================================
python -m streamlit run app.py