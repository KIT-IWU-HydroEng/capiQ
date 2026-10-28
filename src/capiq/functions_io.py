#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

if __name__ == "__main__":
    raise Exception("This file must be run as module")

import json
import logging
import shutil
from pathlib import Path

from user_defined import constants as c


def setup_directories(overwrite: bool = False):
    path_project = Path(c.PROJECT_ROOT)
    folder_input = path_project / "input"
    folder_output = path_project / "output"
    folder_meshes = Path(c.MESH_FOLDER) or path_project / "meshes"
    folder_support = Path(c.SUPPORT_FOLDER) or path_project / "support_files"

    if overwrite and folder_output.exists():
        shutil.rmtree(folder_output)
    folder_output.mkdir(parents=True, exist_ok=True)
    folder_meshes.mkdir(parents=True, exist_ok=True)
    folder_support.mkdir(parents=True, exist_ok=True)

    error_conditions = [
        not folder_input.exists()
        or not any(folder_input.iterdir())
        or not folder_meshes.exists()
        or not any(folder_meshes.iterdir())
    ]

    if any(error_conditions):
        folder_input.mkdir(parents=True, exist_ok=True)
        exception_message = """Input folder is empty. Please add data to the input folder.
        The following structure is expected:
        input
        ├── SCENARIO1_DISCHARGE1_model.json
        ├── SCENARIO1_DISCHARGE1_simulation.json
        ├── SCENARIO2_DISCHARGE2_model.json
        ├── SCENARIO2_DISCHARGE2_simulation.json
        ├── results.json  * This is a single file, and do not need to be personalised for each scenario
        └── ...

        meshes
        ├── file1.2dm
        ├── file2.2dm
        └── ...

        support_files (optional)
        ├── Q001.txt
        ├── Q002.txt
        ├── Q003.txt
        ├── SCENARIO1_DISCHARGE1_Initialization.h5
        └── ...
        """
        raise Exception(exception_message)

    return {
        "path_project": path_project,
        "folder_input": folder_input,
        "folder_output": folder_output,
        "folder_meshes": folder_meshes,
        "folder_support": folder_support,
    }


def write_user_options(user_opt: dict, folder_output: Path, logger: logging.Logger | None = None) -> None:
    user_opt_json_path = folder_output / "capiQ_user_options.json"
    with open(user_opt_json_path, "w") as json_file:
        json.dump(user_opt, json_file, indent=4)

    if logger is not None:
        logger.info("User arguments:")
        for key, value in user_opt.items():
            logger.info(f"\t{key}: {value}")
