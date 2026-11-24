"""Checks the resolution and scheduling of initialization simulations (no BASEMENT needed).

Run from the project root with: pytest tests
"""

import json
import shutil
from pathlib import Path

import pytest

from capiq import basement_tools, calculate_sim_queue, create_sim_queue, functions_io, utils
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
    paths["folder_initialization"].mkdir()
    (paths["folder_initialization"] / INIT_FILE).write_bytes(b"")

    queue = create_sim_queue.create_queue(paths)

    assert queue["produced"] == {}
    assert all(not deps for deps in queue["dependencies"].values())
    assert queue["initialization_files"] == {INIT_FILE: str(paths["folder_initialization"] / INIT_FILE)}


def test_initialization_from_folder_other_name(project):
    """A model asking for "<NAME>_results.h5" uses "<NAME>.h5" from the initialization folder, and back."""
    paths = functions_io.setup_directories()
    paths["folder_initialization"].mkdir()
    (paths["folder_initialization"] / "SCENARIO_Q001.h5").write_bytes(b"")

    queue = create_sim_queue.create_queue(paths)

    assert queue["produced"] == {}
    assert queue["initialization_files"] == {INIT_FILE: str(paths["folder_initialization"] / "SCENARIO_Q001.h5")}

    # The exact name is preferred when both are there
    (paths["folder_initialization"] / INIT_FILE).write_bytes(b"")
    queue = create_sim_queue.create_queue(paths)
    assert queue["initialization_files"] == {INIT_FILE: str(paths["folder_initialization"] / INIT_FILE)}

    # And "<NAME>.h5" asked for, "<NAME>_results.h5" found
    (paths["folder_initialization"] / "SCENARIO_Q001.h5").unlink()
    for name in ["SCENARIO2_Q001", "SCENARIO2_Q002"]:
        set_initial(project / "input" / f"{name}_model.json", "SCENARIO_Q001.h5")
    queue = create_sim_queue.create_queue(paths)
    assert queue["initialization_files"] == {"SCENARIO_Q001.h5": str(paths["folder_initialization"] / INIT_FILE)}


def test_initialization_from_input(project):
    """(2) A missing file produced by a simulation in input/ makes that simulation run first."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    assert queue["produced"] == {INIT_FILE: "SCENARIO_Q001_model.json"}
    assert queue["dependencies"]["SCENARIO2_Q001_model.json"] == {"SCENARIO_Q001_model.json"}
    assert next(iter(queue["simulations_to_run"])) == "SCENARIO_Q001_model.json"


def test_initialization_name_matching(project, monkeypatch):
    """A "<NAME>.h5" in any case is produced by "<NAME>_model.json" and stored under the requested name."""
    for name in ["SCENARIO2_Q001", "SCENARIO2_Q002"]:
        set_initial(project / "input" / f"{name}_model.json", "scenario_q001.H5")
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    assert queue["produced"] == {"scenario_q001.H5": "SCENARIO_Q001_model.json"}

    monkeypatch.setattr(calculate_sim_queue, "calculate", fake_calculate(set(), []))
    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)
    assert (paths["folder_initialization"] / "scenario_q001.H5").read_bytes() == b"results"

    # Next run: found in the initialization folder, whatever the case of the requested name
    for name in ["SCENARIO2_Q001", "SCENARIO2_Q002"]:
        set_initial(project / "input" / f"{name}_model.json", "SCENARIO_Q001.h5")
    queue = create_sim_queue.create_queue(paths)
    assert queue["produced"] == {}
    assert queue["initialization_files"] == {
        "SCENARIO_Q001.h5": str(paths["folder_initialization"] / "scenario_q001.H5")
    }


def test_no_initialization_folder_without_initializations(project, monkeypatch):
    """The initialization folder is not created when no simulation needs initialization."""
    for name in ["SCENARIO2_Q001", "SCENARIO2_Q002"]:
        shutil.copy2(EXAMPLE_FILES / "input" / f"{name}_model.json", project / "input" / f"{name}_model.json")
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    monkeypatch.setattr(calculate_sim_queue, "calculate", fake_calculate(set(), []))

    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)

    assert not paths["folder_initialization"].exists()


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


def test_choose_device():
    assert calculate_sim_queue.choose_device("gpu", gpu_free=True, cpu_free=True) == "gpu"
    assert calculate_sim_queue.choose_device("cpu", gpu_free=True, cpu_free=True) == "cpu"
    # Only one device free: it is used whatever the preference
    assert calculate_sim_queue.choose_device("gpu", gpu_free=False, cpu_free=True) == "cpu"
    assert calculate_sim_queue.choose_device("cpu", gpu_free=True, cpu_free=False) == "gpu"
    assert calculate_sim_queue.choose_device("gpu", gpu_free=False, cpu_free=False) is None


def write_results(sim_config, paths: dict) -> None:
    """Writes a fake final results file where the queue looks for it."""
    subfolders = paths.get("output_subfolders", True)
    results = calculate_sim_queue.results_file(sim_config, Path(paths["folder_output"]), subfolders)
    results.parent.mkdir(parents=True, exist_ok=True)
    results.write_bytes(b"results")


def fake_calculate(fail: set[str], calls: list[str]):
    def calculate(sim_config, paths, user_opts, gpu=False, placement=None):
        name = Path(sim_config).stem.removesuffix("_model")
        calls.append(name)
        if name in fail:
            raise RuntimeError("simulation failed")
        write_results(sim_config, paths)
        return 0.0, None

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


def test_nothing_to_run(project, monkeypatch, caplog):
    """All results exist: the queue stops before detecting hardware or starting workers."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    for model in queue["simulations_to_run"].values():
        write_results(model, paths)

    def fail(*args, **kwargs):
        raise AssertionError("must not be called")

    monkeypatch.setattr(calculate_sim_queue, "calculate", fail)
    monkeypatch.setattr(calculate_sim_queue.cpu_topology, "setup_resources", fail)
    caplog.set_level("INFO")
    options = {"parallel": True, "overwrite": False, "n_gpus": 1, "n_sim_cpus": 2}

    calculate_sim_queue.calculate_queue(queue, paths, {"simulation_options": options})

    assert "Nothing to run" in caplog.text


def test_format_duration():
    assert utils.format_duration(2556.28) == "00d 00h 42min 36s"
    assert utils.format_duration(2 * 86400 + 3 * 3600 + 4 * 60 + 59.9) == "02d 03h 04min 59s"


def test_rts_stats():
    # BASEMENT's RTS is a running average: twice as fast in the first half as in the second
    # (first half 200, second half 100: overall 1 / (0.5 / 200 + 0.5 / 100) = 133.3)
    stdout = (
        " -> Progress: 0/2, dt = 0.001 [s], RTS = 0\n"
        " -> simulation started!\n"
        " -> Progress: 1/2, dt = 0.47 [s], RTS = 200\n"
        " -> Progress: 2/2, dt = 0.05 [s], RTS = 133.333333\n"
        " -> simulation finished at t = 3000.000000 (cpu-time = 2.8485s)\n"
    )
    stats = basement_tools.rts_stats(stdout)
    assert stats.final == pytest.approx(133.33, abs=0.01)
    assert (stats.slowest, stats.fastest) == (pytest.approx(100), pytest.approx(200))

    # Constant speed: the range is a single value
    constant = "".join(f" -> Progress: {k}/4, dt = 0.3 [s], RTS = 500\n" for k in range(5))
    assert basement_tools.rts_stats(constant) == basement_tools.RtsStats(500.0, 500.0, 500.0)

    assert basement_tools.rts_stats("BASEMENT failed") is None


def test_finished_log_line(project, monkeypatch, caplog):
    """The finished line gives the time in seconds and as days/hours/minutes, and the RTS."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    def calculate(sim_config, paths, user_opts, gpu=False, placement=None):
        name = Path(sim_config).stem.removesuffix("_model")
        write_results(sim_config, paths)
        rts = basement_tools.RtsStats(1055.0, 820.4, 6119.2) if name == "SCENARIO_Q001" else None
        return 2556.28, rts

    monkeypatch.setattr(calculate_sim_queue, "calculate", calculate)
    caplog.set_level("INFO")
    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)

    messages = [record.getMessage() for record in caplog.records]
    assert "Simulation SCENARIO_Q001 finished. Elapsed time: 2556.28 seconds (00d 00h 42min 36s)" in messages
    assert "Simulation SCENARIO_Q001 real-time speedup: RTS = 1055.0 (range 820.4-6119.2)" in messages
    # No progress lines in BASEMENT's output: only the time is logged
    assert "Simulation SCENARIO_Q002 finished. Elapsed time: 2556.28 seconds (00d 00h 42min 36s)" in messages
    assert not any(m.startswith("Simulation SCENARIO_Q002 real-time speedup") for m in messages)


def test_output_layout_paths(tmp_path):
    """One folder per simulation by default, all files directly in the output folder otherwise."""
    model = "input/SCENARIO_Q001_model.json"
    assert calculate_sim_queue.simulation_folder(model, tmp_path) == tmp_path / "SCENARIO_Q001"
    assert calculate_sim_queue.results_file(model, tmp_path) == tmp_path / "SCENARIO_Q001" / INIT_FILE
    assert calculate_sim_queue.simulation_folder(model, tmp_path, subfolders=False) == tmp_path
    assert calculate_sim_queue.results_file(model, tmp_path, subfolders=False) == tmp_path / INIT_FILE


@pytest.mark.parametrize("subfolders", [True, False])
def test_output_layout_queue(project, monkeypatch, caplog, subfolders):
    """Results land in the selected layout, initializations are found there, and a rerun skips them."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    calls: list[str] = []
    monkeypatch.setattr(calculate_sim_queue, "calculate", fake_calculate(set(), calls))
    user_opt = {"output_subfolders": subfolders, "simulation_options": {"parallel": False, "overwrite": False}}

    calculate_sim_queue.calculate_queue(queue, paths, user_opt)

    folder_output = Path(paths["folder_output"])
    expected = folder_output / "SCENARIO_Q001" / INIT_FILE if subfolders else folder_output / INIT_FILE
    assert expected.exists()
    assert (paths["folder_initialization"] / INIT_FILE).read_bytes() == b"results"

    caplog.set_level("INFO")
    calculate_sim_queue.calculate_queue(queue, paths, user_opt)
    assert len(calls) == 4
    assert "Nothing to run" in caplog.text


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_make_xdmf_relative(tmp_path, separator):
    """Absolute paths to the xdmf's own folder become bare file names; other paths stay."""
    folder = tmp_path / "SCENARIO_Q001"
    folder.mkdir()
    own = str(folder).replace("\\", separator).replace("/", separator)
    other = "/data" + str(folder).replace("\\", "/")
    xdmf = folder / "SCENARIO_Q001_results.xdmf"
    xdmf.write_text(
        f'<DataItem Format="HDF">{own}{separator}SCENARIO_Q001_results_aux.h5:/CellsAll/HydState</DataItem>\n'
        f'<DataItem Format="HDF">{other}/elsewhere.h5:/x</DataItem>\n',
        encoding="utf-8",
    )

    assert basement_tools.make_xdmf_relative(str(xdmf))
    text = xdmf.read_text(encoding="utf-8")
    assert ">SCENARIO_Q001_results_aux.h5:/CellsAll/HydState<" in text
    assert f">{other}/elsewhere.h5:/x<" in text

    # Already relative: left untouched
    assert not basement_tools.make_xdmf_relative(str(xdmf))
