# Contributing to capiQ

Thank you for your interest in contributing to capiQ, developed by the **Hydraulic Engineering and Water Resources Management** group at the [Institute for Water and Environment (IWU)](https://www.iwu.kit.edu/wb/index.php), [Karlsruhe Institute of Technology (KIT)](https://www.kit.edu).

## Contents

- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Checks](#checks)
- [Tests](#tests)
- [Dependencies](#dependencies)
- [Documentation](#documentation)
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

capiQ uses [uv](https://docs.astral.sh/uv/) to manage its environment (see the [installation instructions](docs/pages/getting-started/installation.md) in the documentation). From the project root:

```bash
uv sync
uv run pre-commit install
```

`uv sync` creates `.venv` and installs capiQ in editable mode, together with the development tools (the `dev` dependency group in `pyproject.toml`), using the exact versions in `uv.lock`. `pre-commit install` sets up the hooks in [.pre-commit-config.yaml](.pre-commit-config.yaml) once per clone: before each commit they fix file endings and trailing whitespace, check TOML and YAML files, block large files, run ruff and mypy, and validate `CITATION.cff` with [cffconvert](https://github.com/citation-file-format/cffconvert) when it changes.

Without uv, install the development tools in an activated virtual environment with `pip install -e . --group dev` (pip 25.1 or newer), then run the commands below without `uv run`.

## Checks

| Task           | Command                                                        |
| -------------- | -------------------------------------------------------------- |
| Run the tests  | `uv run tests/test_all.py`                                     |
| Lint           | `uv run ruff check .`                                          |
| Format         | `uv run ruff format .`                                         |
| Type check     | `uv run mypy`                                                  |
| Security scan  | `uv run bandit -r src -ll`                                     |
| Citation file  | `uv run cffconvert --validate -i CITATION.cff`                 |
| Run all hooks  | `uv run pre-commit run --all-files`                            |
| Build the docs | `uv run zensical build -f docs/zensical.toml --clean --strict` |

To audit the locked runtime dependencies for known vulnerabilities:

```bash
uv export --no-dev --no-emit-project --format requirements-txt -o requirements-audit.txt
uv run pip-audit -r requirements-audit.txt --require-hashes --disable-pip
```

All checks, including the tests (on Linux and Windows, see [Tests](#tests)), also run on GitHub Actions for every pull request and every push to `main` (see [.github/workflows/ci.yml](.github/workflows/ci.yml) and, for the documentation, [.github/workflows/docs.yml](.github/workflows/docs.yml)), together with the organization-wide checks of the pull request title, the citation file, links and the license. They must pass before a pull request is merged.

## Tests

The tests in `tests/` run capiQ on copies of the example files in a temporary folder, so they do not change `example_files/` and you do not need to create the example mesh first. Only `test_example_run` needs BASEMENT; the others replace it with fakes.

- `test_example_files.py`
  - `test_example_queue` checks that the example scenarios find their meshes and support files.
  - `test_example_run` runs all example scenarios with BASEMENT and checks that their results are written. It is skipped if BASEMENT is not found at `BASEMENT_PATH` in `user_defined/constants.py`.
- `test_initialization.py` checks how initialization simulations are found and scheduled (files in the initialization folder, simulations in `input/` that must run first, missing files, cycles, scenarios skipped after a failed initialization), and also the exit codes, the log lines and the output folder layout.
- `test_resume.py` checks how interrupted queues are resumed: complete, partial, damaged and unreadable results files, continuations and their backups, and end times changed after a run started.
- `test_cpu_topology.py` checks the placement on CPU sockets and GPUs (fake Windows and Linux topologies, so no multi-socket machine is needed), the pinned BASEMENT launch, stopping running simulations, the worker processes' log records reaching the capiQ log, and BASEMENT's per-simulation logs.
- `results_files.py` is not a test: it writes the fake BASEMENT results files used by the tests.

Run them all with one command, from any folder:

```bash
uv run tests/test_all.py
```

[tests/test_all.py](tests/test_all.py) runs pytest on `tests/` and ends with a summary of the tests that did not pass, including skipped ones with the reason (e.g. BASEMENT not found). Extra arguments go to pytest: add `-v` to see the result of each test, or `-k "not example_run"` to run only the tests that do not need BASEMENT. `uv run pytest tests` from the project root does the same.

GitHub Actions runs the tests on Linux and Windows for every pull request. BASEMENT is not installed there, so `test_example_run` is skipped. Please run the tests locally before opening a pull request, including `test_example_run` if you have BASEMENT, and add tests for new functionality where possible.

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

## Documentation

The documentation site, <https://kit-iwu-hydroeng.github.io/capiQ/>, is built with [Zensical](https://zensical.org), which `uv sync` installs with the development tools.

- `docs/pages/`: the pages, in Markdown. Every user-facing change should update the page it affects.
- `docs/zensical.toml`: site settings and the navigation. Add new pages to `nav` there.

From the project root, preview the site with live reload at `http://localhost:8000`:

```bash
uv run zensical serve -f docs/zensical.toml
```

Build it as GitHub Actions does; warnings such as broken links or a missing included file stop the build:

```bash
uv run zensical build -f docs/zensical.toml --clean --strict
```

The site is written to `docs/site/`, which is not committed. To show a repository file (an example input, `user_options.yml`, …) on a page, include it with a snippet instead of copying its content, so the page always matches the file. A range of lines can be given with `:start:end`:

````markdown
```json
--8<-- "example_files/input/results.json"
```
````

The workflow [.github/workflows/docs.yml](.github/workflows/docs.yml) builds the site for every pull request and publishes it to GitHub Pages after every push to `main`.

## Workflow

1. Fork the repository (external contributors) or create a branch (group members).
2. Create a descriptively named branch from the default branch, e.g. `fix/initialization-file-lookup` or `feature/parallel-queue`.
3. Make your changes in small, focused commits whose messages follow the [commit message convention](#commit-messages).
4. Run the [checks](#checks) and [tests](#tests), and add tests for new functionality where applicable.
5. Update the [documentation](#documentation) (`docs/pages/`, `README.md`, this file, docstrings) if your change affects usage.
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

- **scope** (optional) names the part of capiQ affected, in parentheses. Suggested scopes follow the modules in `src/capiq/`: `io` (`functions_io.py`), `queue` (`create_sim_queue.py`), `run` (`calculate_sim_queue.py`), `resume` (`resume.py`), `basement` (`basement_tools.py`), `topology` (`cpu_topology.py`), `utils` and `cli` (`__main__.py`).
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
