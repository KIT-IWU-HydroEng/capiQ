# capiQ — Computational Automation Pipeline for Hydro-morphodynamic simulation Queues

capiQ is a Python-based Computational Automation Pipeline for Hydro-morphodynamic simulation Queues, designed to configure, manage, and execute large simulation batches efficiently.

<p align="center">
  <a href="https://github.com/KIT-IWU-HydroEng/capiQ/actions/workflows/ci.yml"><img src="https://github.com/KIT-IWU-HydroEng/capiQ/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://github.com/KIT-IWU-HydroEng/capiQ/releases/latest"><img src="https://img.shields.io/github/v/release/KIT-IWU-HydroEng/capiQ" alt="Latest release"></a>
  <a href="https://github.com/KIT-IWU-HydroEng/capiQ/commits/main"><img src="https://img.shields.io/github/last-commit/KIT-IWU-HydroEng/capiQ" alt="Last commit"></a>
</p>

## What This Repository Contains

- `src/capiq/`: the capiQ package (I/O, queue creation, queue execution, utilities). `__main__.py` is the entry point.
- `user_defined/`: user configuration files (`constants.py` and `user_options.yml`).
- `example_files/`: example input files and support files, to use as templates for your own project, and a script that creates the example mesh.
- `run_capiQ.bat` / `run_capiQ.sh`: run capiQ from the project root on Windows / Linux and macOS (with uv if it is installed, otherwise with `.venv`).
- `pyproject.toml`: package metadata, dependencies and tool settings. `uv.lock` pins the exact version of every dependency, so all installations use the same environment.
- `tests/`: tests that run capiQ with the example files (see [CONTRIBUTING.md](CONTRIBUTING.md#tests)).

Directories used at run time, in the project root:

- `input/`: model and simulation input JSON files. Created on the first run if it is missing, and must then be filled.
- `output/`: generated simulation outputs. Created automatically.

The mesh and support file folders are set in `user_defined/constants.py` and point to `example_files/` by default.

## Installation

Requires [BASEMENT](https://basement.ethz.ch) 4.x (BASEHPC module) and Python 3.11 or newer. The recommended way to install capiQ is with [uv](https://docs.astral.sh/uv/), which also takes care of Python.

On Linux, install BASEMENT's Debian package as described in its manual (`sudo dpkg -i BASEMENT-*.deb`). It puts the executables in `/usr/bin`, which is capiQ's default `BASEMENT_PATH` on Linux (`C:\Program Files\BASEMENT 4.3.0\bin` on Windows; change it in `user_defined/constants.py`).

### 1. Install uv

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Linux and macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for other methods (e.g. `winget`, `pipx` or `brew`).

### 2. Install capiQ

From the project root:

```bash
uv sync
```

This creates the virtual environment `.venv` in the project root and installs capiQ (in editable mode) with the exact dependency versions from `uv.lock`, including the development tools. uv uses any installed Python 3.11 or newer and downloads one only if none is found; to choose a version, add for example `--python 3.12`.

You do not need to activate `.venv`: prefix commands with `uv run` (see [Usage](#usage)), and uv keeps the environment in sync with `uv.lock` before each command.

### Without uv

Create and activate a virtual environment, then install capiQ with pip. This uses the newest dependency versions allowed by `pyproject.toml` instead of the versions in `uv.lock`.

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

**Linux and macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

### 1. Configure user options

1. Edit `user_defined/constants.py` to match your local system paths (BASEMENT installation, mesh and support file folders).
2. Edit `user_defined/user_options.yml` to set your simulation preferences.

#### Required Directory Structure

Ensure the following directories exist and are populated before running:

* `input/`: must include `NAME_model.json`, `NAME_simulation.json`, and a single `results.json`.
* Mesh folder (`MESH_FOLDER` in `constants.py`): include the necessary `.2dm` mesh files.
* Support file folder (`SUPPORT_FOLDER` in `constants.py`): include the discharge `.txt` files used in the `NAME_model.json` files.
* Initialization folder (`INITIALIZATION_FOLDER` in `constants.py`, optional): results files used as initial conditions.

In the `NAME_model.json` files, capiQ only uses the file names of meshes and support files and replaces their paths with the folders above, so any path can be given (e.g. `"discharge_file": "path/to/support_files/Q001.txt"`).

#### Initialization simulations

A scenario can start from the results of another one (`"INITIAL": {"type": "continue", "file": "BASE_Q001_results.h5", "time": 1000.0}` in `HYDRAULICS` or `TURBULENCE`). Before running, capiQ looks for every such file (file names are compared without regard to case):

1. In the initialization folder: the file is used as it is.
2. Otherwise, in `input/`: `BASE_Q001_results.h5` or `BASE_Q001.h5` is produced by `BASE_Q001_model.json`. That simulation runs first, the scenarios that need it start once it has finished, and its results are copied to the initialization folder (created at that point if it does not exist) under the requested name, so later runs find them there.
3. Otherwise, capiQ stops with an error listing the missing files.

If an initialization simulation fails, the scenarios that depend on it are skipped and the others still run; both are listed at the end of the log.

Tip: Templates for these files and folders can be found under the `example_files/` directory. The example mesh is not stored in the repository; create it before running the examples:

```bash
uv run example_files/create_example_mesh.py
```

This writes a light triangular mesh of a rectangular channel to `example_files/meshes/rectangular-channel.2dm`.

### 2. Run

From the project root, so that capiQ finds `user_defined/`:

```bash
uv run python -m capiq
```

Or use the launcher script, which changes to the project root by itself and can therefore be started from anywhere:

**Windows:**
```bash
run_capiQ.bat
```

**Linux and macOS:**
```bash
./run_capiQ.sh
```

The scripts use uv if it is installed and otherwise the `.venv` virtual environment in the project root (capiQ must then be installed in it, see [Without uv](#without-uv)). Arguments are passed on to capiQ, e.g. `--logger-filename` to choose the name of the log file.

Without uv, run `python -m capiq` (and `python example_files/create_example_mesh.py`) with the virtual environment activated.

### Outputs

Upon successful execution, the pipeline generates:

* Results stored in the `output/` directory, by default in one folder per simulation (scenario/discharge combination):

  ```
  output
  ├── capiQ_user_options.json
  ├── SCENARIO_Q001
  │   ├── SCENARIO_Q001_setup.h5
  │   ├── SCENARIO_Q001_results.h5
  │   ├── SCENARIO_Q001_results.xdmf     * open this one in ParaView (with the aux h5 written next to it)
  │   ├── SCENARIO_Q001_basement.log
  │   ├── SCENARIO_Q001_model.json       * with store_configs: True
  │   └── SCENARIO_Q001_simulation.json
  └── SCENARIO_Q002
      └── ...
  ```

  Each folder is self-contained: the `.xdmf` refers to its h5 files by name only, so a folder can be copied or moved elsewhere and still opened in ParaView. Set `output_subfolders: False` in `user_options.yml` to write all files directly in `output/` instead.
* A timestamped log file named `capiQ_YYYY-MM-DD_HH-MM.log` in the project root. For each simulation it gives the elapsed time and BASEMENT's real-time speedup (RTS, overall and the range during the run).
* BASEMENT's own output for each simulation in `<NAME>_basement.log`: setup, simulation (with its progress lines) and results, each with its command and return code, also when BASEMENT fails.

Simulations whose results already exist in `output/` are skipped, so an interrupted queue can be restarted. capiQ looks for them in the layout currently selected: after changing `output_subfolders`, move the existing files accordingly or they are run again. Set `overwrite: true` in `user_options.yml` to run them again. Ctrl+C stops the queue together with the running BASEMENT processes.

### Machines with several CPU sockets or GPUs

On a machine with several CPU sockets, capiQ keeps each simulation inside one socket (on its own cores) and gives each GPU simulation its own card, plus one core on the socket the card is attached to (`pin_to_socket`, `physical_cores_only` and `gpu_numa_nodes` in `user_options.yml`). The log shows where each simulation starts. To see what capiQ detects on a machine:

```bash
uv run python -c "from capiq import cpu_topology; cpu_topology.report()"
```

- **Windows:** tested on multi-socket hardware.
- **Linux:** uses `numactl` if it is installed (`sudo apt-get install numactl`), otherwise `taskset`. **Not tested on real multi-socket Linux hardware: use it at your own risk**, and set `pin_to_socket: false` if simulations fail or slow down.

## Supported hydrodynamic softwares

- BASEMENT 4.x [[1]](#1)[[2]](#2)

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, the checks and tests, managing dependencies with uv, and the commit and pull request conventions.

## Citation

If you use this software in your research, please cite it as described in [CITATION.cff](CITATION.cff) (GitHub shows a *Cite this repository* button).

## References

<a id="1">[1]</a>
Vanzo, D., Peter, S., Vonwiller, L., Bürgler, M., Weberndorfer, M., Siviglia, A., Conde, D., Vetsch, D.F., 2021. basement v3: A modular freeware for river process modelling over multiple computational backends. Environmental Modelling & Software 143, 105102. https://doi.org/10.1016/j.envsoft.2021.105102

<a id="2">[2]</a>
Vetsch, D.F., Frei, S., Halso, M.C., Schierjott, J.C., Bürgler, M., Vanzo, D., 2024. Basement V4—A Multipurpose Modelling Environment for Simulation of Flood Hazards and River Morphodynamics Across Scales, in: Gourbesville, P., Caignaert, G. (Eds.), Advances in Hydroinformatics—SimHydro 2023 Volume 1. Springer Nature, Singapore, pp. 125–138. https://doi.org/10.1007/978-981-97-4072-7_8
