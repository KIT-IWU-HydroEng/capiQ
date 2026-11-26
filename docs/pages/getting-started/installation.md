# Installation

## Requirements

- [BASEMENT](https://basement.ethz.ch) 4.x with the BASEHPC module.
- Python 3.11 or newer. With uv you do not need to install it yourself.
- Windows or Linux. capiQ also runs on macOS, but BASEMENT does not.

The recommended way to install capiQ is with [uv](https://docs.astral.sh/uv/), which also takes care of Python.

## 1. Install uv

=== "Windows (PowerShell)"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "Linux and macOS"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for other methods (e.g. `winget`, `pipx` or `brew`).

## 2. Get capiQ

Clone the repository, or download and unpack a [release](https://github.com/KIT-IWU-HydroEng/capiQ/releases/latest):

```bash
git clone https://github.com/KIT-IWU-HydroEng/capiQ.git
cd capiQ
```

## 3. Install capiQ

From the project root:

```bash
uv sync
```

This creates the virtual environment `.venv` in the project root and installs capiQ (in editable mode) with the exact dependency versions from `uv.lock`, including the development tools. uv uses any installed Python 3.11 or newer and downloads one only if none is found; to choose a version, add for example `--python 3.12`.

You do not need to activate `.venv`: prefix commands with `uv run`, and uv keeps the environment in sync with `uv.lock` before each command.

## 4. Tell capiQ where BASEMENT is

Open `user_defined/constants.py` and check `BASEMENT_PATH`. The default is `C:\Program Files\BASEMENT 4.3.0\bin` on Windows and `/usr/bin` on Linux (BASEMENT's `.deb` package). See [Configuration](../user-guide/configuration.md#paths-constantspy).

Next: run the example with the [quick start](quickstart.md).

## Without uv

Create and activate a virtual environment, then install capiQ with pip. This uses the newest dependency versions allowed by `pyproject.toml` instead of the versions in `uv.lock`.

=== "Windows"

    ```powershell
    python -m venv .venv
    .venv\Scripts\activate
    pip install -e .
    ```

=== "Linux and macOS"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```

Then run the commands in this documentation without `uv run`, with the virtual environment activated.
