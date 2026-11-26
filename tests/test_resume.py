"""Checks resuming and continuing cancelled or crashed simulations (no BASEMENT needed).

Run from the project root with: pytest tests
"""

import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import results_files
from results_files import fake_rerun, write_results
from test_initialization import INIT_FILE, USER_OPT, project  # noqa: F401  (pytest fixture)

from capiq import calculate_sim_queue, create_sim_queue, functions_io, resume

LAYOUTS = ["4.3", "4.2"]


def plan_for(results: Path) -> resume.ResumePlan:
    basename = results.name.removesuffix("_results.h5")
    return resume.plan_resume(results, results.with_suffix(".xdmf"), results.with_name(f"{basename}_setup.h5"))


def with_setup(results: Path) -> Path:
    """The setup file a continuation needs (its content is not read)."""
    results.parent.mkdir(parents=True, exist_ok=True)
    results.with_name(results.name.replace("_results.h5", "_setup.h5")).write_bytes(b"setup")
    return results


# ── Status of a results file ──────────────────────────────────────────────────


@pytest.mark.parametrize("layout", LAYOUTS)
def test_complete_file(tmp_path, layout):
    results = write_results(tmp_path / "A_results.h5", layout=layout)
    status = resume.inspect_results(results)
    assert status.complete and (status.good, status.expected) == (11, 11)
    assert plan_for(results).action == "complete"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_partial_file_continues_from_last_output(tmp_path, layout):
    results = with_setup(write_results(tmp_path / "A_results.h5", 7, layout=layout))
    plan = plan_for(results)
    assert (plan.action, plan.last_index, plan.restart_time, plan.expected) == ("continue", 6, 600.0, 11)
    assert plan.describe() == "continued from t = 600 s (output 6/10, 4 output(s) left)"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_damaged_last_output_falls_back(tmp_path, layout):
    results = with_setup(write_results(tmp_path / "A_results.h5", 7, layout=layout, damage_last=True))
    with h5py.File(results, "r") as file, pytest.raises(OSError):
        file["RESULTS/CellsAll/HydState/0000006"][()]

    plan = plan_for(results)
    assert (plan.action, plan.last_index, plan.restart_time) == ("continue", 5, 500.0)
    assert "output 6 is damaged or incomplete" in plan.describe()


def test_output_missing_in_one_group_falls_back(tmp_path):
    """Killed while writing an output: it is in HydState but not yet in the other groups."""
    results = with_setup(write_results(tmp_path / "A_results.h5", 7))
    with h5py.File(results, "a") as file:
        del file["RESULTS/CellsAll/TrbState/0000006"]
    assert plan_for(results).last_index == 5


def test_start_time_from_output_zero(tmp_path):
    """A continued file stores its restart time as start: the outputs are counted from output 0."""
    results = write_results(tmp_path / "A_results.h5", start=50.0, end=1050.0)
    with h5py.File(results, "a") as file:
        results_files.set_simulation_time(file, 650.0, 1050.0, 100.0)
    status = resume.inspect_results(results)
    assert (status.start, status.expected, status.complete) == (50.0, 11, True)


@pytest.mark.parametrize(
    ("n_written", "damage_last", "reason"),
    [
        (1, False, "no output after t = 0 s"),  # Cancelled before the first output after the start
        (2, True, "no output after t = 0 s"),  # Output 1 damaged: only output 0 is left
        (1, True, "output 0 cannot be read"),
    ],
)
def test_nothing_usable_reruns(tmp_path, n_written, damage_last, reason):
    results = with_setup(write_results(tmp_path / "A_results.h5", n_written, damage_last=damage_last))
    plan = plan_for(results)
    assert plan.action == "scratch" and reason in plan.reason


@pytest.mark.parametrize("content", [b"not an hdf5 file", b"\x89HDF\r\n\x1a\n" + b"\x00" * 40])
def test_unreadable_file_reruns(tmp_path, content):
    results = tmp_path / "A_results.h5"
    results.write_bytes(content)
    plan = plan_for(results)
    assert plan.action == "scratch" and "cannot be read" in plan.reason


def test_truncated_file_reruns(tmp_path):
    results = write_results(tmp_path / "A_results.h5", 7)
    data = results.read_bytes()
    results.write_bytes(data[: len(data) // 3])
    assert plan_for(results).action == "scratch"


def test_no_setup_file_reruns(tmp_path):
    results = write_results(tmp_path / "A_results.h5", 7)
    plan = plan_for(results)
    assert plan.action == "scratch" and "A_setup.h5 missing" in plan.reason


def test_new_and_results_only(tmp_path):
    assert plan_for(tmp_path / "A_results.h5").action == "new"
    # Every output written, but BMv4_results did not run
    results = write_results(tmp_path / "A_results.h5", xdmf=False)
    assert plan_for(results).action == "results_only"


# ── Continuation: backup, re-run, restore ────────────────────────────────────


@pytest.mark.parametrize("layout", LAYOUTS)
def test_continuation_gives_one_complete_file(tmp_path, layout):
    """The continuation appends to the partial file; the output it rewrote and the TIME block are restored."""
    results = with_setup(write_results(tmp_path / "A_results.h5", 7, layout=layout, damage_last=True))
    plan = plan_for(results)

    resume.prepare_continuation(results, plan.last_index)
    backup = resume.backup_file(results)
    assert backup.exists()
    with h5py.File(results, "r") as file:  # The damaged output is removed, so BASEMENT writes it again
        assert "0000006" not in file["RESULTS/CellsAll/HydState"]

    fake_rerun(results, plan.last_index, layout)
    with h5py.File(results, "r") as file:
        assert not file["RESULTS/NodeStrg/HydState/0000005"][()].any()

    resume.finish_continuation(results)
    assert not backup.exists()
    status = resume.inspect_results(results)
    assert status.complete and status.start == 0.0
    with h5py.File(results, "r") as file:
        restored = file["RESULTS/NodeStrg/HydState/0000005"][()]
        assert np.array_equal(restored, results_files.output_values(5, 7, results_files.N_STRINGS))
        assert json.loads(file[".config/simulation"][()])["SIMULATION"]["TIME"]["start"] == 0.0
        assert [float(d.attrs["t"]) for d in file["RESULTS/CellsAll/HydState"].values()] == [
            100.0 * k for k in range(11)
        ]


def test_interrupted_continuation_continues_again(tmp_path):
    """A continuation that is cancelled too is continued from its own last output."""
    results = with_setup(write_results(tmp_path / "A_results.h5", 4))
    resume.prepare_continuation(results, 3)
    fake_rerun(results, 3)
    with h5py.File(results, "a") as file:  # Cancelled after output 7
        for group in results_files.per_output_groups("4.3"):
            for key in ["0000008", "0000009", "0000010"]:
                del file["RESULTS"][group][key]

    plan = plan_for(results)
    assert (plan.action, plan.last_index) == ("continue", 7)
    resume.prepare_continuation(results, plan.last_index)
    fake_rerun(results, plan.last_index)
    resume.finish_continuation(results)

    with h5py.File(results, "r") as file:
        # Both restart outputs hold the original values, not the zeroed ones
        for index in (3, 7):
            values = file[f"RESULTS/NodeStrg/HydState/{index:07d}"][()]
            assert np.array_equal(values, results_files.output_values(index, 7, results_files.N_STRINGS))
    assert resume.inspect_results(results).complete
    assert not resume.backup_file(results).exists()


def test_broken_continuation_restores_backup(tmp_path, caplog):
    """The continuation left an unreadable file: the backup is put back and continued from."""
    results = with_setup(write_results(tmp_path / "A_results.h5", 7))
    resume.prepare_continuation(results, 6)
    results.write_bytes(b"broken")

    caplog.set_level("INFO")
    plan = plan_for(results)
    assert (plan.action, plan.last_index) == ("continue", 6)
    assert not resume.backup_file(results).exists() and resume.inspect_results(results).good == 7
    assert "restored from A_results_backup.h5" in caplog.text


def test_finished_continuation_not_restored_yet(tmp_path):
    """Interrupted between the end of the continuation and the restore: only the restore and results step run."""
    results = with_setup(write_results(tmp_path / "A_results.h5", 7))
    resume.prepare_continuation(results, 6)
    fake_rerun(results, 6)
    assert plan_for(results).action == "finish"


def test_continuation_start(tmp_path):
    source = tmp_path / "A_simulation.json"
    source.write_text(json.dumps({"SIMULATION": {"TIME": {"start": 0.0, "end": 1000.0, "out": 100.0}}}))
    resume.set_continuation_start(source, tmp_path / "A_continue_simulation.json", 600.0)
    written = json.loads((tmp_path / "A_continue_simulation.json").read_text())
    assert written["SIMULATION"]["TIME"] == {"start": 600.0, "end": 1000.0, "out": 100.0}
    assert json.loads(source.read_text())["SIMULATION"]["TIME"]["start"] == 0.0


# ── The queue ─────────────────────────────────────────────────────────────────


def results_of(paths: dict, name: str) -> Path:
    return calculate_sim_queue.results_file(f"{name}_model.json", Path(paths["folder_output"]))


def recording_calculate(plans: dict, fail: set[str] = frozenset()):  # type: ignore[assignment]
    """Fake calculate: records the plan each simulation gets and writes complete results."""

    def calculate(sim_config, paths, user_opts, gpu=False, placement=None, plan=None):
        name = Path(sim_config).stem.removesuffix("_model")
        plans[name] = plan
        if name in fail:
            raise RuntimeError("simulation failed")
        write_results(calculate_sim_queue.results_file(sim_config, Path(paths["folder_output"])))
        return 0.0, None

    return calculate


def test_queue_skips_complete_and_continues_partial(project, monkeypatch, caplog):  # noqa: F811
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    write_results(results_of(paths, "SCENARIO_Q001"))
    with_setup(write_results(results_of(paths, "SCENARIO_Q002"), 7))
    write_results(results_of(paths, "SCENARIO2_Q001"), 1)

    plans: dict = {}
    monkeypatch.setattr(calculate_sim_queue, "calculate", recording_calculate(plans))
    caplog.set_level("INFO")
    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)

    assert "SCENARIO_Q001" not in plans
    assert plans["SCENARIO_Q002"].action == "continue" and plans["SCENARIO_Q002"].last_index == 6
    assert plans["SCENARIO2_Q001"].action == "scratch"
    assert plans["SCENARIO2_Q002"] is None or plans["SCENARIO2_Q002"].action == "new"
    assert "Simulation SCENARIO_Q001: complete (11 outputs), skipped" in caplog.text
    assert "Simulation SCENARIO_Q002: continued from t = 600 s (output 6/10, 4 output(s) left)" in caplog.text
    assert (
        "Simulation SCENARIO2_Q001: rerun from scratch: no output after t = 0 s in SCENARIO2_Q001_results.h5"
        in caplog.text
    )


def test_partial_initialization_is_not_stored(project, monkeypatch):  # noqa: F811
    """A cancelled initialization run is neither skipped nor copied to the initialization folder."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    with_setup(write_results(results_of(paths, "SCENARIO_Q001"), 4))

    # It fails again: nothing in the initialization folder, its dependents are skipped
    plans: dict = {}
    monkeypatch.setattr(calculate_sim_queue, "calculate", recording_calculate(plans, {"SCENARIO_Q001"}))
    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)
    assert plans["SCENARIO_Q001"].action == "continue"
    assert not (paths["folder_initialization"] / INIT_FILE).exists()
    assert "SCENARIO2_Q001" not in plans

    # It is continued to the end: then stored, and its dependents run
    plans.clear()
    monkeypatch.setattr(calculate_sim_queue, "calculate", recording_calculate(plans))
    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)
    assert resume.inspect_results(paths["folder_initialization"] / INIT_FILE).complete
    assert {"SCENARIO2_Q001", "SCENARIO2_Q002"} <= set(plans)


# ── calculate() with BASEMENT replaced by fakes ──────────────────────────────


@pytest.fixture
def fake_basement(monkeypatch):
    """Records the BASEMENT steps; the simulation step writes results as BMv4_simulation would."""
    calls: list[tuple[str, str]] = []
    bt = calculate_sim_queue.bt

    def run_setup(config, setup, *args, **kwargs):
        calls.append(("setup", config))
        Path(setup).write_bytes(b"setup")

    def run_simulation(run_config, setup, results, *args, **kwargs):
        time = json.loads(Path(run_config).read_text())["SIMULATION"]["TIME"]
        calls.append(("simulation", json.dumps(time)))
        if time["start"] == 0.0:
            write_results(Path(results), xdmf=False)
        else:
            fake_rerun(Path(results), round(time["start"] / time["out"]), end=time["end"])
        return {"stdout": "", "stderr": "", "returncode": 0}

    def run_results(config, results, xdmf, *args, **kwargs):
        calls.append(("results", xdmf))
        Path(xdmf).write_text("<Xdmf/>\n")

    monkeypatch.setattr(bt, "run_setup", run_setup)
    monkeypatch.setattr(bt, "run_simulation", run_simulation)
    monkeypatch.setattr(bt, "run_results", run_results)
    return calls


def test_calculate_continues(project, fake_basement):  # noqa: F811
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    results = with_setup(write_results(results_of(paths, "SCENARIO_Q002"), 7))
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    input_simulation = Path(model).with_name("SCENARIO_Q002_simulation.json").read_text()
    local_paths = {**paths, "meshes": queue["meshes"], "support_files": queue["support_files"]}
    plan = plan_for(results)

    calculate_sim_queue.calculate(model, local_paths, USER_OPT, plan=plan)

    # No setup step, the simulation started at the last good output, then the results step
    assert [step for step, _ in fake_basement] == ["simulation", "results"]
    assert json.loads(fake_basement[0][1]) == {"end": 1000.0, "out": 100.0, "start": 600.0}
    assert resume.inspect_results(results).complete
    assert calculate_sim_queue.simulation_completed(model, Path(paths["folder_output"]))
    assert Path(model).with_name("SCENARIO_Q002_simulation.json").read_text() == input_simulation
    leftovers = {p.name for p in results.parent.iterdir()} - {
        "SCENARIO_Q002_results.h5",
        "SCENARIO_Q002_results.xdmf",
        "SCENARIO_Q002_setup.h5",
        "SCENARIO_Q002_model.json",
        "SCENARIO_Q002_simulation.json",
    }
    assert leftovers == set()


@pytest.mark.parametrize("store_configs", [True, False])
def test_calculate_keeps_input_model(project, fake_basement, store_configs):  # noqa: F811
    """The input model file is never changed: the setup reads a copy with full paths in the output folder."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = Path(queue["simulations_to_run"]["SCENARIO_Q001_model.json"])
    original = model.read_bytes()
    local_paths = {**paths, "meshes": queue["meshes"], "support_files": queue["support_files"]}
    user_opt = {**USER_OPT, "store_configs": store_configs}

    calculate_sim_queue.calculate(model, local_paths, user_opt)

    assert model.read_bytes() == original
    setup_model = paths["folder_output"] / "SCENARIO_Q001" / "SCENARIO_Q001_model.json"
    assert fake_basement[0] == ("setup", str(setup_model))
    # Kept as the record of what BASEMENT read only with store_configs; the simulation file is a plain copy
    assert setup_model.exists() == store_configs
    if store_configs:
        setup = json.loads(setup_model.read_text())["SETUP"]
        assert setup["simulation_name"] == "SCENARIO_Q001_model"
        mesh = setup["BASEHPC"]["BASEPLANE_2D"]["GEOMETRY"]["mesh_file"]
        assert mesh == str(paths["folder_meshes"] / "rectangular-channel.2dm")
        simulation = setup_model.with_name("SCENARIO_Q001_simulation.json")
        assert simulation.read_bytes() == model.with_name("SCENARIO_Q001_simulation.json").read_bytes()


def test_calculate_scratch_moves_unusable_file(project, fake_basement):  # noqa: F811
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    results = results_of(paths, "SCENARIO_Q002")
    results.parent.mkdir(parents=True)
    results.write_bytes(b"broken")
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    local_paths = {**paths, "meshes": queue["meshes"], "support_files": queue["support_files"]}

    calculate_sim_queue.calculate(model, local_paths, USER_OPT, plan=plan_for(results))

    assert [step for step, _ in fake_basement] == ["setup", "simulation", "results"]
    assert resume.unusable_file(results).read_bytes() == b"broken"
    assert resume.inspect_results(results).complete


def test_calculate_raises_on_incomplete_results(project, fake_basement, monkeypatch):  # noqa: F811
    """BASEMENT returned without error but did not write every output: the run fails."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    local_paths = {**paths, "meshes": queue["meshes"], "support_files": queue["support_files"]}

    def short_run(run_config, setup, results, *args, **kwargs):
        write_results(Path(results), 5)
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(calculate_sim_queue.bt, "run_simulation", short_run)
    with pytest.raises(RuntimeError, match="5 of 11 outputs"):
        calculate_sim_queue.calculate(model, local_paths, USER_OPT)


# ── End time changed in the input after the run started ──────────────────────


def set_input_time(model: Path, **time: float) -> Path:
    """Changes SIMULATION.TIME of the input "<NAME>_simulation.json" next to a model file."""
    run_config = Path(model).with_name(Path(model).name.replace("_model.json", "_simulation.json"))
    data = json.loads(run_config.read_text())
    data["SIMULATION"]["TIME"].update(time)
    run_config.write_text(json.dumps(data, indent=2))
    return run_config


def test_shortened_end_continues_to_new_end(project, fake_basement):  # noqa: F811
    """Cancelled at t = 400 s of 1000 s, then the end is shortened to 700 s: continued to 700 s only."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    results = with_setup(write_results(results_of(paths, "SCENARIO_Q002"), 5))
    set_input_time(model, end=700.0)

    plan = calculate_sim_queue.resume_plan(model, Path(paths["folder_output"]))
    assert (plan.action, plan.last_index, plan.expected) == ("continue", 4, 8)
    assert plan.describe() == "continued from t = 400 s (output 4/7, 3 output(s) left)"

    local_paths = {**paths, "meshes": queue["meshes"], "support_files": queue["support_files"]}
    calculate_sim_queue.calculate(model, local_paths, USER_OPT, plan=plan)

    assert json.loads(fake_basement[0][1]) == {"end": 700.0, "out": 100.0, "start": 400.0}
    with h5py.File(results, "r") as file:
        # Original start, new end: the completeness check uses the end the run was planned with
        assert json.loads(file[".config/simulation"][()])["SIMULATION"]["TIME"] == {
            "end": 700.0,
            "out": 100.0,
            "start": 0.0,
        }
        assert len(file["RESULTS/CellsAll/HydState"]) == 8
    assert resume.inspect_results(results).complete
    assert calculate_sim_queue.simulation_completed(model, Path(paths["folder_output"]))


def test_shortened_end_already_reached(project, fake_basement):  # noqa: F811
    """Cancelled at t = 800 s of 1000 s, then the end is shortened to 600 s: only the results step runs."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    results = with_setup(write_results(results_of(paths, "SCENARIO_Q002"), 9))
    set_input_time(model, end=600.0)

    plan = calculate_sim_queue.resume_plan(model, Path(paths["folder_output"]))
    assert (plan.action, plan.expected) == ("results_only", 7)

    local_paths = {**paths, "meshes": queue["meshes"], "support_files": queue["support_files"]}
    calculate_sim_queue.calculate(model, local_paths, USER_OPT, plan=plan)

    assert [step for step, _ in fake_basement] == ["results"]
    with h5py.File(results, "r") as file:
        assert json.loads(file[".config/simulation"][()])["SIMULATION"]["TIME"]["end"] == 600.0
    assert calculate_sim_queue.simulation_completed(model, Path(paths["folder_output"]))


def test_lengthened_end_continues_complete_run(project):  # noqa: F811
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    with_setup(write_results(results_of(paths, "SCENARIO_Q002")))
    assert calculate_sim_queue.resume_plan(model, Path(paths["folder_output"])).action == "complete"

    set_input_time(model, end=1500.0)
    plan = calculate_sim_queue.resume_plan(model, Path(paths["folder_output"]))
    assert (plan.action, plan.last_index, plan.restart_time, plan.expected) == ("continue", 10, 1000.0, 16)


@pytest.mark.parametrize(
    ("time", "reason"),
    [
        ({"out": 50.0}, "output interval changed from 100 s to 50 s"),
        ({"start": 100.0}, "start time changed from 0 s to 100 s"),
    ],
)
def test_changed_output_times_rerun(project, time, reason):  # noqa: F811
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    with_setup(write_results(results_of(paths, "SCENARIO_Q002"), 5))
    set_input_time(model, **time)
    plan = calculate_sim_queue.resume_plan(model, Path(paths["folder_output"]))
    assert (plan.action, plan.reason) == ("scratch", reason)


def test_shortened_end_after_complete_run_is_skipped(project, fake_basement, caplog):  # noqa: F811
    """A finished run whose end is shortened afterwards stays complete and untouched (only overwrite reruns it)."""
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)
    model = queue["simulations_to_run"]["SCENARIO_Q002_model.json"]
    results = with_setup(write_results(results_of(paths, "SCENARIO_Q002")))
    before = results.read_bytes()
    set_input_time(model, end=600.0)

    caplog.set_level("INFO")
    calculate_sim_queue.calculate_queue(queue, paths, USER_OPT)

    assert (
        "Simulation SCENARIO_Q002: complete (7 outputs; holds outputs up to t = 1000 s, after the end 600 s), skipped"
        in caplog.text
    )
    assert results.read_bytes() == before  # Not trimmed, its stored TIME not changed
