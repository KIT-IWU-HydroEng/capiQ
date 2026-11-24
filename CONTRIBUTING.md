# Contributing to capiQ

Thank you for your interest in contributing to capiQ, developed by the **Hydraulic Engineering and Water Resources Management** group at the [Institute for Water and Environment (IWU)](https://www.iwu.kit.edu/wb/index.php), [Karlsruhe Institute of Technology (KIT)](https://www.kit.edu).

## Contents

- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Checks](#checks)
- [Tests](#tests)
- [Dependencies](#dependencies)
- [Workflow](#workflow)
- [Commit messages](#commit-messages)
- [Code guidelines](#code-guidelines)
- [Research data and scientific integrity](#research-data-and-scientific-integrity)
- [Licensing](#licensing)
- [Code of conduct](#code-of-conduct)

## Ways to contribute

- **Report bugs**: open an [issue](https://github.com/KIT-IWU-HydroEng/capiQ/issues) describing the problem, the steps to reproduce it, the expected and the actual behaviour, and your environment (operating system, Python, capiQ and BASEMENT versions). Attach the capiQ log file (`capiQ_YYYY-MM-DD_HH-MM.log`) if it helps.
- **Suggest improvements**: open an issue explaining the idea and the use case behind it.
- **Improve documentation**: corrections and clarifications are always welcome.
- **Contribute code**: fix bugs, add features or tests via pull requests.

Before starting larger changes, please open an issue first so the scope can be discussed with the maintainers.

## Development setup

capiQ uses [uv](https://docs.astral.sh/uv/) to manage its environment (see the [installation instructions](README.md#installation) in the README). From the project root:

```bash
uv sync
uv run pre-commit install
```

`uv sync` creates `.venv` and installs capiQ in editable mode, together with the development tools (the `dev` dependency group in `pyproject.toml`), using the exact versions in `uv.lock`. `pre-commit install` sets up the hooks in [.pre-commit-config.yaml](.pre-commit-config.yaml) once per clone: before each commit they fix file endings and trailing whitespace, check TOML and YAML files, block large files and run ruff and mypy.

Without uv, install the development tools in an activated virtual environment with `pip install -e . --group dev` (pip 25.1 or newer), then run the commands below without `uv run`.

## Checks

| Task          | Command                             |
| ------------- | ----------------------------------- |
| Run the tests | `uv run pytest tests`               |
| Lint          | `uv run ruff check .`               |
| Format        | `uv run ruff format .`              |
| Type check    | `uv run mypy`                       |
| Security scan | `uv run bandit -r src -ll`          |
| Run all hooks | `uv run pre-commit run --all-files` |

To audit the locked runtime dependencies for known vulnerabilities:

```bash
uv export --no-dev --no-emit-project --format requirements-txt -o requirements-audit.txt
uv run pip-audit -r requirements-audit.txt --require-hashes --disable-pip
```

All checks except the tests also run on GitHub Actions for every push and pull request (see [.github/workflows/ci.yml](.github/workflows/ci.yml)), together with the organization-wide checks of the pull request title, the citation file, links and the license. They must pass before a pull request is merged.

## Tests

The tests in `tests/` run capiQ on copies of the example files in a temporary folder, so they do not change `example_files/` and you do not need to create the example mesh first.

- `test_example_files.py`
  - `test_example_queue` checks that the example scenarios find their meshes and support files.
  - `test_example_run` runs all example scenarios with BASEMENT and checks that their results are written. It is skipped if BASEMENT is not found at `BASEMENT_PATH` in `user_defined/constants.py`.
- `test_initialization.py` checks how initialization simulations are found and scheduled: files in the initialization folder, simulations in `input/` that must run first, missing files, cycles, and scenarios skipped after a failed initialization.

Run them from the project root:

```bash
uv run pytest tests
```

Add `-v` to see the result of each test, or `-k "not example_run"` to run only the tests that do not need BASEMENT.

Because `test_example_run` needs BASEMENT, the tests only run locally, not on GitHub Actions. Please run them, including `test_example_run` if you have BASEMENT, before opening a pull request, and add tests for new functionality where possible.

## Dependencies

Keep dependencies to a minimum. Declare them in `pyproject.toml` with uv, which also updates `uv.lock`:

| Task                       | Command                               |
| -------------------------- | ------------------------------------- |
| Add a runtime dependency   | `uv add <package>`                    |
| Add a development tool     | `uv add --dev <package>`              |
| Remove a dependency        | `uv remove <package>`                 |
| Update all locked versions | `uv lock --upgrade`                   |
| Update one package         | `uv lock --upgrade-package <package>` |

Commit `uv.lock` together with every change to the dependencies in `pyproject.toml`. GitHub Actions fails if `uv.lock` is out of date (`uv lock --check`). Use the `build` commit type for these changes, e.g. `build: update locked dependencies`.

## Workflow

1. Fork the repository (external contributors) or create a branch (group members).
2. Create a descriptively named branch from the default branch, e.g. `fix/initialization-file-lookup` or `feature/parallel-queue`.
3. Make your changes in small, focused commits whose messages follow the [commit message convention](#commit-messages).
4. Run the [checks](#checks) and [tests](#tests), and add tests for new functionality where applicable.
5. Update the documentation (`README.md`, this file, docstrings) if your change affects usage.
6. Open a pull request against the default branch, describing what was changed and why, and referencing related issues (e.g. `Closes #12`). Fill in the pull request template. The pull request title must also follow the commit message convention, as it is used as the commit message when pull requests are squash-merged.
7. A maintainer will review the pull request. Please be responsive to feedback; changes may be requested before merging.

## Commit messages

All commit messages, and pull request titles, must follow the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) specification:

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

- **type** describes the kind of change. Use one of:

  | Type       | Use for                                                        |
  | ---------- | -------------------------------------------------------------- |
  | `feat`     | a new feature                                                  |
  | `fix`      | a bug fix                                                      |
  | `docs`     | documentation only                                             |
  | `style`    | formatting that does not change the code's meaning             |
  | `refactor` | code changes that neither fix a bug nor add a feature          |
  | `perf`     | performance improvements                                       |
  | `test`     | adding or correcting tests                                     |
  | `build`    | the build system or dependencies (`pyproject.toml`, `uv.lock`) |
  | `ci`       | continuous integration configuration                           |
  | `chore`    | other maintenance that does not touch source code or tests     |
  | `revert`   | reverting an earlier commit                                    |

- **scope** (optional) names the part of capiQ affected, in parentheses. Suggested scopes follow the modules in `src/capiq/`: `io` (`functions_io.py`), `queue` (`create_sim_queue.py`), `run` (`calculate_sim_queue.py`), `basement` (`basement_tools.py`), `utils` and `cli` (`__main__.py`).
- **description** is a short summary in the imperative mood ("add", not "added" or "adds"), starting in lowercase and without a full stop at the end.
- **body** (optional) explains what changed and why, separated from the description by a blank line.
- **footer** (optional) references issues (e.g. `Refs: #12`) or other metadata.
- **Breaking changes**, i.e. changes that break existing usage such as the input JSON files, `user_options.yml`, `constants.py` or command-line options, are marked with `!` after the type or scope and/or a `BREAKING CHANGE:` footer.

Examples:

```text
feat(queue): start scenarios from the results of an initialization simulation
```

```text
fix(io): keep the file name when replacing the mesh path

Only the folder was replaced, so meshes given with a relative path were
not found in MESH_FOLDER.

Refs: #42
```

```text
feat(cli)!: rename --logger-filename to --log-file

BREAKING CHANGE: scripts that pass --logger-filename must use --log-file.
```

## Code guidelines

- Follow the style and conventions already used in the repository. Formatting and linting are enforced by ruff (line length 120, settings in `pyproject.toml`); type hints are checked by mypy.
- Put package code in `src/capiq/`. `user_defined/` holds user configuration and is not part of the package; do not commit personal paths in `user_defined/constants.py`.
- Write readable code and comment non-obvious steps, especially physical assumptions, units and numerical choices.
- Do not commit large raw datasets, meshes, model outputs (`input/`, `output/`, results `.h5` files), credentials or personal data. Example data belongs in `example_files/`, kept small; the example mesh is generated by `example_files/create_example_mesh.py` instead of being stored.
- New files in `src/capiq/` and new scripts start with the SPDX license and copyright header used in the existing ones.

## Research data and scientific integrity

capiQ is used to run simulations for scientific studies. When contributing:

- Do not change results-relevant code silently; document changes that may affect simulation setups or results (e.g. how input files are written or which simulations are run).
- Cite sources for methods, equations or code adapted from other work.
- If you use capiQ in your research, please cite it as described in [CITATION.cff](CITATION.cff).

## Licensing

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) of this repository. See [LICENSING.md](https://github.com/KIT-IWU-HydroEng/.github/blob/main/.github/LICENSING.md) for more information.

## Code of conduct

Everyone participating in this repository is expected to follow our [Code of Conduct](https://github.com/KIT-IWU-HydroEng/.github/blob/main/.github/CODE_OF_CONDUCT.md).
