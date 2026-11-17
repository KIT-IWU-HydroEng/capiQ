"""Checks the resolution and scheduling of initialization simulations (no BASEMENT needed).

Run from the project root with: pytest tests
"""

import json
import shutil
from pathlib import Path

import pytest

from capiq import calculate_sim_queue, create_sim_queue, functions_io
from user_defined import constants

EXAMPLE_FILES = Path(__file__).resolve().parent.parent / "example_files"
INIT_FILE = "SCENARIO_Q001_results.h5"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Temporary project where SCENARIO2_Q001 and SCENARIO2_Q002 start from the results of SCENARIO_Q001."""
    for folder in ["input", "support_files"]:
        shutil.copytree(EXAMPLE_FILES / folder, tmp_path / folder)
    (tmp_path / "meshes").mkdir()
    (tmp_path / "meshes" / "rectangular-channel.2dm").write_text("MESH2D\n")

    for name in ["SCENARIO2_Q001", "SCENARIO2_Q002"]:
        set_initial(tmp_path / "input" / f"{name}_model.json", f"path/to/{INIT_FILE}")

    monkeypatch.setattr(constants, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(constants, "MESH_FOLDER", tmp_path / "meshes")
    monkeypatch.setattr(constants, "SUPPORT_FOLDER", tmp_path / "support_files")
    monkeypatch.setattr(constants, "INITIALIZATION_FOLDER", tmp_path / "initialization")
    return tmp_path


def set_initial(model_file: Path, init_file: str) -> None:
    data = json.loads(model_file.read_text())
    initial = {"type": "continue", "file": init_file, "time": 1000.0}
    data["SETUP"]["BASEHPC"]["BASEPLANE_2D"]["HYDRAULICS"]["INITIAL"] = initial
    model_file.write_text(json.dumps(data, indent=4))


def test_initialization_from_folder(project):
    """(1) A file present in the initialization folder is used as it is."""
    paths = functions_io.setup_directories()
    (paths["folder_initialization"] / INIT_FILE).write_bytes(b"")

    queue = create_sim_queue.create_queue(paths)

    assert queue["produced"] == {}
    assert all(not deps for deps in queue["dependencies"].values())
    assert queue["initialization_files"] == {INIT_FILE: str(paths["folder_initialization"] / INIT_FILE)}


def test_initialization_from_input(project):
    """(2) A missing file produced by a simulation in input/ makes that simulation run first."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    assert queue["produced"] == {INIT_FILE: "SCENARIO_Q001_model.json"}
    assert queue["dependencies"]["SCENARIO2_Q001_model.json"] == {"SCENARIO_Q001_model.json"}
    assert next(iter(queue["simulations_to_run"])) == "SCENARIO_Q001_model.json"


def test_initialization_missing(project):
    """(3) A file found neither in the initialization folder nor in input/ raises an error."""
    set_initial(project / "input" / "SCENARIO_Q002_model.json", "UNKNOWN_results.h5")
    paths = functions_io.setup_directories()

    with pytest.raises(FileNotFoundError, match="UNKNOWN_results.h5"):
        create_sim_queue.create_queue(paths)


def test_initialization_cycle(project):
    """Simulations that initialize each other raise an error."""
    set_initial(project / "input" / "SCENARIO_Q001_model.json", "SCENARIO2_Q001_results.h5")
    paths = functions_io.setup_directories()

    with pytest.raises(Exception, match="Circular"):
        create_sim_queue.create_queue(paths)


def test_ready_simulations():
    dependencies = {"b": {"a"}, "c": {"b"}, "d": set()}
    ready, blocked = calculate_sim_queue.ready_simulations(["b", "c", "d"], dependencies, set(), set())
    assert ready == ["d"] and blocked == []

    ready, blocked = calculate_sim_queue.ready_simulations(["b", "c", "d"], dependencies, {"a"}, set())
    assert ready == ["b", "d"] and blocked == []

    ready, blocked = calculate_sim_queue.ready_simulations(["b", "c", "d"], dependencies, set(), {"a"})
    assert ready == ["d"] and blocked == ["b"]


def fake_calculate(fail: set[str], calls: list[str]):
    def calculate(sim_config, paths, user_opts, gpu=False):
        name = Path(sim_config).stem.removesuffix("_model")
        calls.append(name)
        if name in fail:
            raise RuntimeError("simulation failed")
        (Path(paths["folder_output"]) / f"{name}_results.h5").write_bytes(b"results")
        return 0.0

    return calculate


USER_OPT = {"simulation_options": {"parallel": False, "overwrite": False}}


def test_sequential_runs_initialization_first(project, monkeypatch):
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    calls: list[str] = []
    monkeypatch.setattr(calculate_sim_queue, "calculate", fake_calculate(set(), calls))

    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)

    assert calls[0] == "SCENARIO_Q001"
    assert sorted(calls) == ["SCENARIO2_Q001", "SCENARIO2_Q002", "SCENARIO_Q001", "SCENARIO_Q002"]
    assert (paths["folder_initialization"] / INIT_FILE).read_bytes() == b"results"


def test_sequential_skips_dependents_of_failed_initialization(project, monkeypatch):
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    calls: list[str] = []
    monkeypatch.setattr(calculate_sim_queue, "calculate", fake_calculate({"SCENARIO_Q001"}, calls))

    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)

    assert sorted(calls) == ["SCENARIO_Q001", "SCENARIO_Q002"]
    assert not (paths["folder_initialization"] / INIT_FILE).exists()
