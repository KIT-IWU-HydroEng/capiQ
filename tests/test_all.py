#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

"""Runs all of capiQ's tests in one go, from any folder.

    uv run tests/test_all.py

Without uv, run `python tests/test_all.py` with the virtual environment activated. Extra arguments
go to pytest, e.g. `uv run tests/test_all.py -v` (one line per test) or
`uv run tests/test_all.py -k "not example_run"`.

The summary at the end lists the skipped tests with the reason: test_example_run runs only when
BASEMENT is found at BASEMENT_PATH in user_defined/constants.py.

This file holds no tests itself: pytest collects it and finds nothing to run.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main(args: list[str]) -> int:
    import pytest

    # The tests import user_defined/ and capiq/ from the project root
    os.chdir(PROJECT_ROOT)
    # -ra: summary of every test that did not pass (failed, error, skipped with its reason)
    return int(pytest.main(["tests", "-ra", *args]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
