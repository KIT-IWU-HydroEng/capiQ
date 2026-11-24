@echo off
:: SPDX-License-Identifier: MIT
:: Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
:: Author: Luiz Oliveira
:: Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

setlocal

:: Resolve the project root to an absolute path without a trailing backslash.
set "PROJECT_ROOT=%~dp0"
for %%I in ("%PROJECT_ROOT%.") do set "PROJECT_ROOT=%%~fI"

:: capiQ reads user_defined/ relative to the project root, so run from there.
cd /d "%PROJECT_ROOT%"

:: Preferred: uv creates or updates .venv from uv.lock, then runs capiQ in it.
where uv >nul 2>nul
if %errorlevel% neq 0 goto :no_uv
uv run python -m capiq %*
exit /b %errorlevel%

:no_uv
:: Fallback without uv: use the virtual-environment Python located in the repository.
:: The package must be installed in it: pip install -e .
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
	echo ERROR: uv was not found and the Python executable does not exist:
	echo   "%PYTHON_EXE%"
	echo Install uv ^(https://docs.astral.sh/uv/^) or create .venv and run: pip install -e .
	exit /b 1
)

"%PYTHON_EXE%" -m capiq %*
exit /b %errorlevel%
