#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

"""
Sets up the project folders of a run and records its user options in the output folder.
"""

if __name__ == "__main__":
    raise Exception("This file must be run as module")

import json
import logging
import shutil
from pathlib import Path

from user_defined import constants as c

# Shown when the input or mesh folder is empty: the layout of the documentation's "Input files" page,
# drawn in ASCII so that every terminal shows it (box-drawing characters break on cp1252 consoles)
EXPECTED_LAYOUT = """Add the files, then run capiQ again. The following layout is expected:

input/                               (project root)
|-- SCENARIO_Q001_model.json         one pair per simulation
|-- SCENARIO_Q001_simulation.json
|-- SCENARIO_Q002_model.json
|-- SCENARIO_Q002_simulation.json
`-- results.json                     a single file for all simulations

MESH_FOLDER/                         (constants.py)
`-- rectangular-channel.2dm

SUPPORT_FOLDER/                      (constants.py)
|-- Q001.txt
`-- Q002.txt

INITIALIZATION_FOLDER/               (constants.py, optional)
`-- BASE_Q001_results.h5"""


def setup_directories(overwrite: bool = False):
    """
    Finds the project folders (set in ``user_defined/constants.py``) and creates the missing output, mesh and
    support folders.

    Args:
        overwrite: Delete the output folder first.

    Returns:
        paths (dict): The paths ``path_project``, ``folder_input``, ``folder_output``, ``folder_meshes``,
            ``folder_support`` and ``folder_initialization``.

    Raises:
        Exception: If the input or the mesh folder is missing or empty; the message shows the expected layout.
    """
    path_project = Path(c.PROJECT_ROOT)
    folder_input = path_project / "input"
    folder_output = path_project / "output"
    folder_meshes = Path(c.MESH_FOLDER) or path_project / "meshes"
    folder_support = Path(c.SUPPORT_FOLDER) or path_project / "support_files"
    folder_initialization = Path(getattr(c, "INITIALIZATION_FOLDER", None) or path_project / "initialization")

    if overwrite and folder_output.exists():
        shutil.rmtree(folder_output)
    folder_output.mkdir(parents=True, exist_ok=True)
    folder_meshes.mkdir(parents=True, exist_ok=True)
    folder_support.mkdir(parents=True, exist_ok=True)
    # The initialization folder is only created when an initialization result has to be stored in it

    # Names every folder that is missing or empty, then the expected layout
    problems = []
    if not folder_input.exists():
        problems.append(f"The input folder {folder_input} does not exist: it was created now.")
    elif not any(folder_input.iterdir()):
        problems.append(f"The input folder {folder_input} is empty.")
    if not any(folder_meshes.iterdir()):
        problems.append(f"The mesh folder {folder_meshes} (MESH_FOLDER in user_defined/constants.py) is empty.")

    if problems:
        folder_input.mkdir(parents=True, exist_ok=True)
        raise Exception("\n".join([*problems, EXPECTED_LAYOUT]))

    return {
        "path_project": path_project,
        "folder_input": folder_input,
        "folder_output": folder_output,
        "folder_meshes": folder_meshes,
        "folder_support": folder_support,
        "folder_initialization": folder_initialization,
    }


def write_user_options(user_opt: dict, folder_output: Path, logger: logging.Logger | None = None) -> None:
    """
    Writes the user options of the run to ``capiQ_user_options.json`` in the output folder.

    Args:
        user_opt: The user options (``user_defined/user_options.yml``).
        folder_output: The output folder.
        logger: If given, the options are also written to this log.
    """
    user_opt_json_path = folder_output / "capiQ_user_options.json"
    with open(user_opt_json_path, "w") as json_file:
        json.dump(user_opt, json_file, indent=4)

    if logger is not None:
        logger.info("User arguments:")
        for key, value in user_opt.items():
            logger.info(f"\t{key}: {value}")
