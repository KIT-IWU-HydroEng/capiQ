"""Checks that capiQ runs with the files in example_files/.

Run from the project root with: pytest tests
"""

import runpy
import shutil
from pathlib import Path

import pytest

from capiq import basement_tools, create_sim_queue, functions_io
from capiq.__main__ import main
from user_defined import constants

EXAMPLE_FILES = Path(__file__).resolve().parent.parent / "example_files"
BASEMENT_FOUND = (Path(constants.BASEMENT_PATH) / "BMv4_setup.exe").exists()

# The example mesh is not part of the repository: it is created by this script
write_rectangular_mesh = runpy.run_path(str(EXAMPLE_FILES / "create_example_mesh.py"))["write_rectangular_mesh"]


@pytest.fixture
def example_project(tmp_path, monkeypatch):
    """Copy the example files into a temporary project, create the mesh and point capiQ to it.

    capiQ rewrites the model files in input/, so it must not run on example_files/ directly.
    """
    for folder in ["input", "support_files"]:
        shutil.copytree(EXAMPLE_FILES / folder, tmp_path / folder)
    write_rectangular_mesh(tmp_path / "meshes" / "rectangular-channel.2dm")

    monkeypatch.setattr(constants, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(constants, "MESH_FOLDER", tmp_path / "meshes")
    monkeypatch.setattr(constants, "SUPPORT_FOLDER", tmp_path / "support_files")
    return tmp_path


def test_example_queue(example_project):
    """The example scenarios find their meshes and support files (no BASEMENT needed)."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    assert len(queue["simulations_to_run"]) == 4

    # Same file lookup as calculate_sim_queue.calculate: fails if a referenced file is missing
    available_files = {**queue["meshes"], **queue["support_files"]}
    for model_file in queue["simulations_to_run"].values():
        basement_tools.model_update_filepaths(model_file, available_files)


@pytest.mark.skipif(not BASEMENT_FOUND, reason=f"BASEMENT not found in {constants.BASEMENT_PATH}")
def test_example_run(example_project):
    """capiQ runs all example scenarios with BASEMENT and writes their results."""
    user_opt = {
        "store_configs": True,
        "simulation_options": {"verbose": False, "parallel": False, "overwrite": False, "n_sim_threads": 4},
    }
    main(user_opt, logger_filename=str(example_project / "capiQ.log"))

    for model_file in (EXAMPLE_FILES / "input").glob("*_model.json"):
        name = model_file.stem.removesuffix("_model")
        for suffix in ["_setup.h5", "_results.h5", "_results.xdmf"]:
            assert (example_project / "output" / f"{name}{suffix}").exists(), f"missing {name}{suffix}"
