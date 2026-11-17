# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

"""
Defines project-wide path constants used by the configuration modules.

Attributes
----------
PROJECT_ROOT : pathlib.Path
    Root directory of the repository (one level above this file's parent directory).
BASEMENT_PATH : str
    Installation path to the BASEMENT executable binaries.
MESH_FOLDER : pathlib.Path
    Directory containing mesh input files.
SUPPORT_FOLDER : pathlib.Path
    Directory containing supplementary discharge files.
INITIALIZATION_FOLDER : pathlib.Path
    Directory containing initialization results files (``<NAME>_results.h5``) used by
    ``INITIAL`` sections of the model files. Missing files are produced by running
    ``input/<NAME>_model.json`` first, and the results are copied here for later runs.
"""

import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Constants for the project
# The paths can also be full paths if needed, using pathlib allows for relative paths that are more flexible across different environments.
BASEMENT_PATH = r"C:\Program Files\BASEMENT 4.3.0\bin"
MESH_FOLDER = PROJECT_ROOT / "example_files" / "meshes"
SUPPORT_FOLDER = PROJECT_ROOT / "example_files" / "support_files" # Contains discharge files for the simulations.
INITIALIZATION_FOLDER = PROJECT_ROOT / "example_files" / "initialization" # Contains initialization (<NAME>_results.h5) files.
