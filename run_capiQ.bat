@echo off
:: SPDX-License-Identifier: MIT
:: Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
:: Author: Luiz Oliveira
:: Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

setlocal

:: Resolve the project root to an absolute path without a trailing backslash.
set "PROJECT_ROOT=%~dp0"
for %%I in ("%PROJECT_ROOT%.") do set "PROJECT_ROOT=%%~fI"

:: Use the virtual-environment Python located in the repository.
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
	echo ERROR: Python executable not found:
	echo   "%PYTHON_EXE%"
	exit /b 1
)

:: capiQ reads user_defined/ relative to the project root, so run from there.
:: The package must be installed in the virtual environment: pip install -e .
cd /d "%PROJECT_ROOT%"
"%PYTHON_EXE%" -m capiq
exit /b %errorlevel%
