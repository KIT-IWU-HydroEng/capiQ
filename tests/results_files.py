"""Small synthetic BASEMENT results files for the tests (no BASEMENT needed).

Layout as written by BMv4_simulation: ".config/simulation" holds the SIMULATION block, and every
output k is a dataset "RESULTS/<entity>/<variable>/%07d" with its time in the attribute "t".
BASEMENT 4.3 stores the bed elevation per output (RESULTS/CellsAll/BottomEl/%07d),
4.2 once (here: the dataset RESULTS/CellsAll/BottomEl).
"""

import json
from pathlib import Path

import h5py
import numpy as np

N_CELLS = 10
N_STRINGS = 2


def per_output_groups(layout: str) -> dict[str, int]:
    """{group under RESULTS: number of columns} of the groups holding one dataset per output."""
    groups = {"CellsAll/HydState": 3, "CellsAll/TrbState": 6, "NodeStrg/HydState": 7}
    if layout == "4.3":
        groups["CellsAll/BottomEl"] = 1
    return groups


def output_values(index: int, columns: int, rows: int = N_CELLS) -> np.ndarray:
    """Values of an output: different for each output, so restored or rewritten outputs can be told apart."""
    return np.full((rows, columns), float(index + 1))


def write_output(file: h5py.File, layout: str, index: int, time: float, damaged: bool = False) -> None:
    """Writes output ``index`` in every per-output group; ``damaged`` makes its HydState chunked and compressed."""
    for group, columns in per_output_groups(layout).items():
        rows = N_STRINGS if group.startswith("NodeStrg") else N_CELLS
        values = output_values(index, columns, rows)
        if group in file["RESULTS"] and f"{index:07d}" in file["RESULTS"][group]:
            del file["RESULTS"][group][f"{index:07d}"]
        if damaged and group == "CellsAll/HydState":
            dataset = (
                file["RESULTS"]
                .require_group(group)
                .create_dataset(f"{index:07d}", data=values, chunks=values.shape, compression="gzip")
            )
        else:
            dataset = file["RESULTS"].require_group(group).create_dataset(f"{index:07d}", data=values)
        dataset.attrs["t"] = np.float64(time)


def set_simulation_time(file: h5py.File, start: float, end: float, out: float) -> None:
    config = {"SIMULATION": {"OUTPUT": ["water_depth"], "TIME": {"end": end, "out": out, "start": start}}}
    if "simulation" in file[".config"]:
        del file[".config/simulation"]
    file[".config"].create_dataset("simulation", data=json.dumps(config, separators=(",", ":")).encode())


def write_results(
    path: Path,
    n_written: int | None = None,
    *,
    start: float = 0.0,
    end: float = 1000.0,
    out: float = 100.0,
    layout: str = "4.3",
    damage_last: bool = False,
    xdmf: bool | None = None,
) -> Path:
    """
    Writes a results file holding outputs 0..n_written-1 (all of them if None).

    Args:
        path: "<NAME>_results.h5".
        n_written: Number of outputs written (a cancelled run writes fewer than expected).
        start, end, out: SIMULATION.TIME of the run.
        layout: "4.3" or "4.2".
        damage_last: Makes the last written output unreadable.
        xdmf: Also writes "<NAME>_results.xdmf"; default: only when every output is written.
    """
    expected = round((end - start) / out) + 1
    n_written = expected if n_written is None else n_written
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as file:
        file.create_group(".config").create_dataset("model", data=b"{}")
        set_simulation_time(file, start, end, out)
        file.create_dataset("CellsAll/Topology", data=np.zeros((N_CELLS, 3), dtype=np.int32))
        results = file.create_group("RESULTS")
        if layout == "4.2":
            results.create_dataset("CellsAll/BottomEl", data=np.zeros((N_CELLS, 1)))
        for index in range(n_written):
            write_output(file, layout, index, start + index * out, damaged=damage_last and index == n_written - 1)

    if damage_last and n_written > 0:
        damage_dataset(path, f"RESULTS/CellsAll/HydState/{n_written - 1:07d}")
    if xdmf if xdmf is not None else n_written == expected:
        path.with_suffix(".xdmf").write_text("<Xdmf/>\n")
    return path


def damage_dataset(path: Path, name: str) -> None:
    """Overwrites the compressed chunk of a dataset on disk, so reading it fails (as after a crash)."""
    with h5py.File(path, "r") as file:
        info = file[name].id.get_chunk_info(0)
        offset, size = info.byte_offset, info.size
    with open(path, "r+b") as raw:
        raw.seek(offset)
        raw.write(b"\xff" * size)


def fake_rerun(path: Path, restart_index: int, layout: str = "4.3", end: float | None = None) -> None:
    """
    What BASEMENT's re-run does to the results file, as observed with BASEMENT 4.3.0:
    rewrites the output at the restart time (nodestring fluxes zeroed, like an output 0),
    appends the remaining outputs and stores the restart time as SIMULATION.TIME.start.
    ``end``: SIMULATION.TIME.end of the continuation (default: the one stored in the file).
    """
    with h5py.File(path, "a") as file:
        time = json.loads(file[".config/simulation"][()].decode())["SIMULATION"]["TIME"]
        start = float(file["RESULTS/CellsAll/HydState/0000000"].attrs["t"])
        end, out = float(time["end"]) if end is None else end, float(time["out"])
        expected = round((end - start) / out) + 1
        for index in range(restart_index, expected):
            write_output(file, layout, index, start + index * out)
        file[f"RESULTS/NodeStrg/HydState/{restart_index:07d}"][...] = 0.0
        set_simulation_time(file, start + restart_index * out, end, out)
