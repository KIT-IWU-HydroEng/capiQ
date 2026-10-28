# capiQ — Computational Automation Pipeline for Hydro-morphodynamic simulation Queues

capiQ is a Python-based Computational Automation Pipeline for Hydro-morphodynamic simulation Queues, designed to configure, manage, and execute large simulation batches efficiently.

## What This Repository Contains

- `src/capiq/`: the capiQ package (I/O, queue creation, queue execution, utilities). `__main__.py` is the entry point.
- `user_defined/`: user configuration files (`constants.py` and `user_options.yml`).
- `example_files/`: example input files and support files, to use as templates for your own project, and a script that creates the example mesh.
- `run_capiQ.bat`: runs capiQ with the virtual environment of the repository (Windows).
- `tests/`: tests that run capiQ with the example files (see [Development](#development)).

Directories used at run time, in the project root:

- `input/`: model and simulation input JSON files. Created on the first run if it is missing, and must then be filled.
- `output/`: generated simulation outputs. Created automatically.

The mesh and support file folders are set in `user_defined/constants.py` and point to `example_files/` by default.

## Installation

Requires Python 3.11 or newer and [BASEMENT](https://basement.ethz.ch) 4.x.

### 1. Create and activate a virtual environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Unix**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install capiQ

From the project root:

```bash
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
* Support file folder (`SUPPORT_FOLDER` in `constants.py`): include the discharge `.txt` files and initialization files used in the `NAME_model.json` files.

In the `NAME_model.json` files, capiQ only uses the file names of meshes and support files and replaces their paths with the folders above, so any path can be given (e.g. `"discharge_file": "path/to/support_files/Q001.txt"`).

Tip: Templates for these files and folders can be found under the `example_files/` directory. The example mesh is not stored in the repository; create it before running the examples:

```bash
python example_files/create_example_mesh.py
```

This writes a light rectangular mesh (720 cells, two friction zones) to `example_files/meshes/rectangular-channel.2dm`.

### 2. Run

From the project root, so that capiQ finds `user_defined/`:

```bash
python -m capiq
```

On Windows, you can also run `run_capiQ.bat`, which uses the `.venv` virtual environment in the project root (capiQ must be installed in it, see [Installation](#installation)). Use `--logger-filename` to choose the name of the log file.

### Outputs

Upon successful execution, the pipeline generates:

* Results stored in the `output/` directory
* A timestamped log file named `capiQ_YYYY-MM-DD_HH-MM.log` in the project root.

Simulations whose results already exist in `output/` are skipped, so an interrupted queue can be restarted. Set `overwrite: true` in `user_options.yml` to run them again.

## Supported hydrodynamic softwares

- BASEMENT 4.x [[1]](#1)[[2]](#2)

## Development

Install the package in editable mode with the development tools, and set up the pre-commit hooks:

```bash
pip install -e ".[dev]"
pre-commit install
```

| Task                      | Command             |
| ------------------------- | ------------------- |
| Run the tests             | `pytest tests`      |
| Lint                      | `ruff check .`      |
| Format                    | `ruff format .`     |
| Type check                | `mypy`              |
| Security scan             | `bandit -r src -ll` |
| Audit dependencies        | `pip-audit .`       |

These checks, except the tests, also run on GitHub Actions for every push and pull request (see [.github/workflows/](.github/workflows/)).

### Tests

The tests in `tests/` check that capiQ runs with the example files:

- `test_example_queue` checks that the example scenarios find their meshes and support files. It does not need BASEMENT.
- `test_example_run` runs all example scenarios with BASEMENT and checks that their results are written. It is skipped if BASEMENT is not found at `BASEMENT_PATH` in `user_defined/constants.py`.

To run them, install the development tools (see above) and run, from the project root:

```bash
pytest tests
```

Add `-v` to see the result of each test, or `-k example_queue` to run only the test that does not need BASEMENT. The tests create the example mesh and copy the example files into a temporary folder, so they do not change `example_files/` and you do not need to create the mesh first.

Because they need BASEMENT, the tests only run locally, not on GitHub Actions.

## Citation

If you use this software in your research, please cite it as described in [CITATION.cff](CITATION.cff) (GitHub shows a *Cite this repository* button).

## References

<a id="1">[1]</a>
Vanzo, D., Peter, S., Vonwiller, L., Bürgler, M., Weberndorfer, M., Siviglia, A., Conde, D., Vetsch, D.F., 2021. basement v3: A modular freeware for river process modelling over multiple computational backends. Environmental Modelling & Software 143, 105102. https://doi.org/10.1016/j.envsoft.2021.105102

<a id="2">[2]</a>
Vetsch, D.F., Frei, S., Halso, M.C., Schierjott, J.C., Bürgler, M., Vanzo, D., 2024. Basement V4—A Multipurpose Modelling Environment for Simulation of Flood Hazards and River Morphodynamics Across Scales, in: Gourbesville, P., Caignaert, G. (Eds.), Advances in Hydroinformatics—SimHydro 2023 Volume 1. Springer Nature, Singapore, pp. 125–138. https://doi.org/10.1007/978-981-97-4072-7_8
