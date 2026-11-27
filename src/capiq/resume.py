#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637
"""
Decides whether a simulation is complete, can be continued, or has to run from the start.

BASEMENT writes "<NAME>_results.h5" while it runs, so a cancelled or crashed run leaves a
partial file behind. Every output k is a dataset "RESULTS/<entity>/<variable>/%07d" with its
time in the attribute "t", in every per-output group (4.3: HydState, BottomEl, TrbState, ...;
4.2 stores the bed elevation once, outside these groups). ".config/simulation" holds the
SIMULATION block (TIME start/end/out) the run was started with.

A partial run is continued with BASEMENT's re-run (User Manual 3.5): the same setup file,
the partial results file as output and SIMULATION.TIME.start = time of its last output.
BASEMENT then appends the remaining outputs to the same file, with the same keys and times
as an uninterrupted run. It rewrites the output at the restart time like an output 0
(nodestring fluxes zeroed) and stores start = restart time in ".config/simulation", so both
are restored from a backup copy afterwards (``finish_continuation``).
Checked with BASEMENT 4.3.0: files left by a hard kill open with h5py, and the outputs
written before the kill read back completely.
"""

if __name__ == "__main__":
    raise Exception("This file must be run as module")

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import h5py

logger = logging.getLogger("resume")

# Name of an output dataset: its index, zero-padded to 7 digits
OUTPUT_KEY = re.compile(r"^\d{7}$")

Action = Literal["new", "complete", "results_only", "finish", "continue", "scratch"]


@dataclass(frozen=True)
class ResultsStatus:
    """What a results file holds."""

    readable: bool
    error: str = ""  # Why the file cannot be used, if it cannot
    start: float = 0.0  # Time of output 0
    end: float = 0.0
    out: float = 0.0
    expected: int = 0  # Number of outputs the simulation asked for
    good: int = 0  # Outputs 0..good-1 read back completely
    present: int = 0  # Outputs found in the file (also damaged or incomplete ones)

    @property
    def complete(self) -> bool:
        return self.readable and self.expected > 0 and self.good >= self.expected

    def time(self, index: int) -> float:
        return self.start + index * self.out


@dataclass(frozen=True)
class ResumePlan:
    """What to do with a simulation when the queue starts."""

    action: Action
    reason: str = ""
    last_index: int = -1  # "continue": last output that reads back completely
    restart_time: float = 0.0  # "continue": its time, the start of the continuation
    expected: int = 0  # Number of outputs of the whole simulation

    def describe(self) -> str:
        """Log text: what happens and why."""
        if self.action == "new":
            return "runs from the start (no results yet)"
        note = f"; {self.reason}" if self.reason else ""
        if self.action == "complete":
            return f"complete ({self.expected} outputs{note}), skipped"
        if self.action == "results_only":
            return f"all {self.expected} outputs present{note}, but no .xdmf: only the results step runs"
        if self.action == "finish":
            return f"all {self.expected} outputs present ({self.reason}): only the results step runs"
        if self.action == "continue":
            left = self.expected - 1 - self.last_index
            return (
                f"continued from t = {self.restart_time:g} s "
                f"(output {self.last_index}/{self.expected - 1}, {left} output(s) left)"
                + (f": {self.reason}" if self.reason else "")
            )
        return f"rerun from scratch: {self.reason}"


def backup_file(results_path: Path) -> Path:
    """Copy of the partial results kept while a continuation runs."""
    return results_path.with_name(results_path.stem + "_backup.h5")


def unusable_file(results_path: Path) -> Path:
    """Name an unusable results file is moved to before the simulation runs again."""
    return results_path.with_name(results_path.stem + "_unusable.h5")


def _output_groups(file: h5py.File) -> list[str]:
    """Paths of the groups under RESULTS that hold one dataset per output."""
    groups: list[str] = []
    if "RESULTS" not in file:
        return groups

    def visit(name: str, obj) -> None:
        if isinstance(obj, h5py.Group) and any(OUTPUT_KEY.match(key) for key in obj):
            groups.append(f"RESULTS/{name}")

    file["RESULTS"].visititems(visit)
    return groups


def _simulation_config(file: h5py.File) -> dict:
    """The SIMULATION block the results file was written with (".config/simulation")."""
    raw = file[".config/simulation"][()]
    if isinstance(raw, bytes):
        raw = raw.decode()
    config: dict = json.loads(str(raw))
    return config


def _simulation_time(file: h5py.File) -> tuple[float, float, float]:
    """SIMULATION.TIME (start, end, out) the results file was written with."""
    time = _simulation_config(file)["SIMULATION"]["TIME"]
    return float(time["start"]), float(time["end"]), float(time["out"])


def read_simulation_time(run_config: Path) -> tuple[float, float, float] | None:
    """
    SIMULATION.TIME (start, end, out) of "<NAME>_simulation.json", or None if it cannot be read.

    The input file is what the run is planned from: its end may have changed since the run started.
    """
    try:
        time = json.loads(Path(run_config).read_text())["SIMULATION"]["TIME"]
        return float(time["start"]), float(time["end"]), float(time["out"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _output_ok(file: h5py.File, groups: list[str], index: int, expected_time: float, out: float) -> bool:
    """Whether output ``index`` is in every per-output group and reads back completely at the right time."""
    key = f"{index:07d}"
    for group in groups:
        if key not in file[group]:
            return False
        dataset = file[group][key]
        dataset[()]  # Reads the whole dataset: raises if it is damaged
        if abs(float(dataset.attrs["t"]) - expected_time) > 1e-6 * max(1.0, abs(out)):
            return False
    return True


def inspect_results(results_path: Path, end_out: tuple[float, float] | None = None) -> ResultsStatus:
    """
    Reads a results file and counts the outputs that read back completely.

    The start time is the time of output 0, not SIMULATION.TIME.start: a continued run stores
    its restart time there. The number of expected outputs is round((end - start) / out) + 1.
    Outputs after the end (the end was shortened) are counted too: they do not make a run incomplete.

    Args:
        results_path: "<NAME>_results.h5".
        end_out: SIMULATION.TIME end and out to check against (from the input "<NAME>_simulation.json");
                 None uses the ones stored in the file.

    Returns:
        The status of the file; ``readable`` is False if it cannot be opened or has no output 0.
    """
    try:
        with h5py.File(results_path, "r") as file:
            _, end, out = _simulation_time(file)
            if end_out is not None:
                end, out = end_out
            groups = _output_groups(file)
            if not groups or out <= 0:
                return ResultsStatus(False, "no outputs in the file")
            keys = {key for group in groups for key in file[group] if OUTPUT_KEY.match(key)}
            present = len(keys)
            hydstate = file.get("RESULTS/CellsAll/HydState", file[groups[0]])
            if "0000000" not in hydstate:
                return ResultsStatus(False, "output 0 missing", present=present)
            start = float(hydstate["0000000"].attrs["t"])
            expected = round((end - start) / out) + 1

            good = 0
            for index in range(max(expected, present)):
                try:
                    if not _output_ok(file, groups, index, start + index * out, out):
                        break
                except Exception:  # A damaged dataset raises from the HDF5 library
                    break
                good += 1
    except Exception as exc:
        return ResultsStatus(False, f"cannot be read ({type(exc).__name__}: {exc})")

    if good == 0:
        return ResultsStatus(False, "output 0 cannot be read", present=present)
    return ResultsStatus(True, "", start, end, out, expected, good, present)


def plan_resume(results_path: Path, xdmf_path: Path, setup_path: Path, run_config: Path | None = None) -> ResumePlan:
    """
    Decides how a simulation continues from what it left in its output folder.

    - No results file: "new".
    The outputs are counted against SIMULATION.TIME of the input "<NAME>_simulation.json", not the one
    stored in the results file: its end may have changed since the run started (shortened: a run that
    already holds every output of the new end is finished; lengthened: a complete run is continued).

    - Every output there and the .xdmf too (written only after the simulation succeeded): "complete".
    - Every output there, no .xdmf: "results_only" (BMv4_results failed or was interrupted).
    - Some outputs after the start and the setup file there: "continue" from the last output that
      reads back completely. A backup from an earlier, interrupted continuation is used if the
      results file itself is unusable or holds fewer outputs.
    - Otherwise "scratch", with the reason.

    Args:
        results_path: "<NAME>_results.h5".
        xdmf_path: "<NAME>_results.xdmf".
        setup_path: "<NAME>_setup.h5", needed by the continuation.
        run_config: Input "<NAME>_simulation.json"; None (or unreadable) uses the TIME stored in the results.
    """
    backup = backup_file(results_path)
    if not results_path.exists() and not backup.exists():
        return ResumePlan("new")

    planned = read_simulation_time(run_config) if run_config is not None else None
    end_out = (planned[1], planned[2]) if planned is not None else None
    status = inspect_results(results_path, end_out) if results_path.exists() else ResultsStatus(False, "missing")
    if backup.exists():
        saved = inspect_results(backup, end_out)
        if saved.readable and (not status.readable or saved.good > status.good):
            # The continuation broke the file or wrote nothing usable: start over from the backup
            why = status.error or f"{status.good} outputs, backup {saved.good}"
            os.replace(backup, results_path)
            logger.info(f"{results_path.name} restored from {backup.name} ({why})")
            status = saved

    if not status.readable:
        return ResumePlan("scratch", f"{results_path.name} {status.error}")
    if planned is not None:
        # The outputs written so far must fit the planned times
        with h5py.File(results_path, "r") as file:
            _, _, stored_out = _simulation_time(file)
        if abs(planned[2] - stored_out) > 1e-9 * max(1.0, stored_out):
            return ResumePlan("scratch", f"output interval changed from {stored_out:g} s to {planned[2]:g} s")
        if abs(planned[0] - status.start) > 1e-9 * max(1.0, abs(status.start)):
            return ResumePlan("scratch", f"start time changed from {status.start:g} s to {planned[0]:g} s")
    if status.complete:
        if backup.exists():
            # Continuation finished, but the output at its restart time was not restored yet
            return ResumePlan("finish", "continuation finished, restoring its restart output", expected=status.expected)
        # The end was shortened after the run got past it: the later outputs are kept, not trimmed
        beyond = ""
        if status.good > status.expected:
            beyond = f"holds outputs up to t = {status.time(status.good - 1):g} s, after the end {status.end:g} s"
        if xdmf_path.exists():
            # Only overwrite: true runs a finished simulation again
            return ResumePlan("complete", beyond, expected=status.expected)
        return ResumePlan("results_only", beyond, expected=status.expected)

    last = status.good - 1
    if last < 1:
        return ResumePlan("scratch", f"no output after t = {status.start:g} s in {results_path.name}")
    if not setup_path.exists():
        return ResumePlan("scratch", f"{setup_path.name} missing, needed to continue")

    reason = ""
    if status.present > status.good:
        reason = f"output {status.good} is damaged or incomplete"
    return ResumePlan("continue", reason, last, status.time(last), status.expected)


def _drop_outputs_after(file: h5py.File, last_index: int) -> None:
    """Deletes every output after ``last_index`` (damaged or incomplete ones), so BASEMENT writes them again."""
    for group in _output_groups(file):
        for key in [key for key in file[group] if OUTPUT_KEY.match(key) and int(key) > last_index]:
            del file[group][key]


def _restore_restart_output(backup: Path, results_path: Path) -> None:
    """
    Copies the last complete output of the backup into the results file.

    BASEMENT's re-run writes the output at its restart time again (nodestring fluxes zeroed, like an
    output 0); the backup holds the original.
    """
    saved = inspect_results(backup)
    if not saved.readable:
        return
    key = f"{saved.good - 1:07d}"
    with h5py.File(backup, "r") as source, h5py.File(results_path, "a") as target:
        for group in _output_groups(source):
            if key in source[group] and group in target:
                if key in target[group]:
                    del target[group][key]
                source.copy(source[group][key], target[group], key)


def set_simulation_time(results_path: Path, end: float, out: float) -> None:
    """
    Writes SIMULATION.TIME into ".config/simulation": start = time of output 0 (the original start,
    also after a continuation, which stores its restart time there), end and out as planned.
    The rest of the stored SIMULATION block is kept.
    """
    with h5py.File(results_path, "a") as file:
        config = _simulation_config(file)
        groups = _output_groups(file)
        hydstate = file.get("RESULTS/CellsAll/HydState", file[groups[0]] if groups else None)
        if hydstate is None or "0000000" not in hydstate:
            return
        start = float(hydstate["0000000"].attrs["t"])
        time = config["SIMULATION"]["TIME"]
        if (float(time["start"]), float(time["end"]), float(time["out"])) == (start, end, out):
            return
        time.update({"start": start, "end": end, "out": out})
        del file[".config/simulation"]
        file[".config"].create_dataset("simulation", data=json.dumps(config, separators=(",", ":")).encode())


def prepare_continuation(results_path: Path, last_index: int) -> None:
    """
    Backs up the partial results and removes the outputs after ``last_index`` from them.

    The backup is a copy, since BASEMENT appends to the results file itself. A backup left by an
    earlier, interrupted continuation first gives back the output it restarted from, then is refreshed.
    """
    backup = backup_file(results_path)
    if backup.exists():
        _restore_restart_output(backup, results_path)
    # Copied before the file is changed, so the backup always holds what the interrupted run left
    shutil.copy2(results_path, backup)
    with h5py.File(results_path, "a") as file:
        _drop_outputs_after(file, last_index)


def finish_continuation(results_path: Path, end: float | None = None, out: float | None = None) -> None:
    """
    After the simulation step: restores the output at the restart time of a continuation and removes
    the backup, then stores the original start and the planned end and out in ".config/simulation",
    so the completeness check and BMv4_results use the end the run was planned with.

    Args:
        results_path: "<NAME>_results.h5".
        end: SIMULATION.TIME end of the input "<NAME>_simulation.json";
            None keeps the one stored in the file.
        out: SIMULATION.TIME out of the input "<NAME>_simulation.json";
            None keeps the one stored in the file.
    """
    backup = backup_file(results_path)
    if backup.exists():
        _restore_restart_output(backup, results_path)
        backup.unlink()
    with h5py.File(results_path, "r") as file:
        _, stored_end, stored_out = _simulation_time(file)
    set_simulation_time(results_path, stored_end if end is None else end, stored_out if out is None else out)


def set_continuation_start(run_config: Path, target: Path, restart_time: float) -> None:
    """Writes a copy of "<NAME>_simulation.json" whose SIMULATION.TIME.start is the restart time."""
    data = json.loads(Path(run_config).read_text())
    data["SIMULATION"]["TIME"]["start"] = restart_time
    Path(target).write_text(json.dumps(data, indent=2))
