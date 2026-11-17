"""Checks socket detection, core and GPU allocation and the pinned launch (no BASEMENT or multi-socket machine needed).

Run from the project root with: pytest tests
"""

import concurrent.futures
import logging
import re
import struct
import threading
import time
from pathlib import Path

import pytest
from test_initialization import project  # noqa: F401  (fixture: example project in a temporary folder)

from capiq import basement_tools, calculate_sim_queue, cpu_topology, create_sim_queue, functions_io
from capiq.cpu_topology import CoreAllocator, GpuInfo, GpuSlots, NumaNode, Placement


def numa_record(node: int, group: int, mask: int) -> bytes:
    body = struct.pack("<I18xH", node, 1) + struct.pack("<QH6x", mask, group)
    return struct.pack("<II", 1, 8 + len(body)) + body


def core_record(group: int, mask: int) -> bytes:
    smt = 1 if bin(mask).count("1") > 1 else 0
    body = struct.pack("<BB20xH", smt, 0, 1) + struct.pack("<QH6x", mask, group)
    return struct.pack("<II", 0, 8 + len(body)) + body


def two_sockets_smt() -> list[NumaNode]:
    """2 x 8 cores with hyper-threading, one processor group per socket."""
    numa = numa_record(0, 0, (1 << 16) - 1) + numa_record(1, 1, (1 << 16) - 1)
    cores = b"".join(core_record(group, 0b11 << (2 * i)) for group in (0, 1) for i in range(8))
    return cpu_topology.parse_topology(numa, cores)


def two_sockets() -> list[NumaNode]:
    """2 x 8 cores without hyper-threading, both sockets in one processor group."""
    numa = numa_record(0, 0, (1 << 8) - 1) + numa_record(1, 0, ((1 << 8) - 1) << 8)
    cores = b"".join(core_record(0, 1 << i) for i in range(16))
    return cpu_topology.parse_topology(numa, cores)


def test_parse_topology_with_smt():
    nodes = two_sockets_smt()
    assert [(n.node_id, n.group, len(n.cores)) for n in nodes] == [(0, 0, 8), (1, 1, 8)]
    assert nodes[1].cores[0] == (0, 1) and nodes[1].base == 0


def test_parse_topology_one_group():
    nodes = two_sockets()
    assert [(n.node_id, n.group, len(n.cores)) for n in nodes] == [(0, 0, 8), (1, 0, 8)]
    assert nodes[1].cores[0] == (8,) and nodes[1].base == 8


def test_allocator_spreads_and_never_overlaps():
    cores = CoreAllocator(two_sockets())
    placements = [cores.acquire(4) for _ in range(4)]

    assert [p.node_id for p in placements] == [0, 1, 0, 1]
    assert placements[1].cpus == tuple(range(8, 12))
    # Masks for start /NODE are relative to the socket's first CPU
    assert [p.node_mask for p in placements] == [0xF, 0xF, 0xF0, 0xF0]
    assert cores.acquire(4) is None

    cores.release(placements[1])
    assert cores.acquire(4) == placements[1]


def test_allocator_physical_cores_only():
    placement = CoreAllocator(two_sockets_smt()).acquire(4)
    assert placement.cpus == (0, 2, 4, 6) and placement.node_mask == 0x55

    placement = CoreAllocator(two_sockets_smt(), physical_only=False).acquire(4)
    assert placement.cpus == (0, 1, 2, 3) and placement.node_mask == 0xF


def test_allocator_fits_one_socket():
    assert CoreAllocator(two_sockets()).fits(8)
    assert not CoreAllocator(two_sockets()).fits(9)
    assert not CoreAllocator(two_sockets_smt()).fits(9)
    assert CoreAllocator(two_sockets_smt(), physical_only=False).fits(16)


def test_gpu_on_its_socket():
    cores = CoreAllocator(two_sockets())
    gpus = GpuSlots([GpuInfo(0, 0), GpuInfo(1, 1)], 2)

    slot0, first = gpus.acquire(cores)
    slot1, second = gpus.acquire(cores)
    assert (first.cuda_device, first.node_id, first.cpus) == (0, 0, (0,))
    assert (second.cuda_device, second.node_id, second.cpus) == (1, 1, (8,))
    assert not gpus.free()

    # The host cores are taken from the CPU runs: 7 free cores left on each socket
    assert cores.free_cores(0) == cores.free_cores(1) == 7

    gpus.release(slot0)
    cores.release(first)
    assert cores.free_cores(0) == 8


def test_gpu_prefers_socket_with_free_core():
    cores = CoreAllocator(two_sockets())
    cores.acquire(8, node_id=0)
    _, placement = GpuSlots([GpuInfo(0, 0), GpuInfo(1, 1)], 2).acquire(cores)
    assert (placement.cuda_device, placement.node_id) == (1, 1)


def test_gpu_least_busy_card_and_unknown_socket():
    gpus = GpuSlots([GpuInfo(0, None), GpuInfo(1, None)], 3)
    devices = [gpus.acquire(None)[1].cuda_device for _ in range(2)]
    assert devices == [0, 1]

    _, placement = GpuSlots([GpuInfo(0, None)], 1).acquire(CoreAllocator(two_sockets()))
    assert placement == Placement(cuda_device=0)

    # Without nvidia-smi the card is left to BASEMENT
    assert GpuSlots(None, 2).acquire(None)[1].cuda_device is None


def test_parse_pnp_numa():
    # An adapter without NUMA node is skipped; a single adapter comes as a dict
    data = [{"bus": 193, "address": 0, "numa": 1}, {"bus": None, "address": None, "numa": None}]
    assert cpu_topology.parse_pnp_numa(data) == {(193, 0, 0): 1}
    assert cpu_topology.parse_pnp_numa({"bus": 5, "address": (3 << 16) | 1, "numa": 0}) == {(5, 3, 1): 0}


def test_parse_nvidia_smi():
    output = "0, 00000000:41:00.0\n1, 00000000:C1:00.0\n"
    assert cpu_topology.parse_nvidia_smi(output) == [(0, (0x41, 0, 0)), (1, (0xC1, 0, 0))]


def test_pinned_command_and_env():
    placement = Placement(node_id=1, cpus=tuple(range(8, 12)), node_mask=0xF, cuda_device=1)
    command = cpu_topology.pinned_command([r"C:\BASEMENT 4\BMv4_simulation.exe", "a b.json"], placement)
    assert command == (
        'cmd /d /c "start "" /B /WAIT /NODE 1 /AFFINITY 0xf "C:\\BASEMENT 4\\BMv4_simulation.exe" "a b.json" & exit"'
    )
    env = cpu_topology.launch_env(placement)
    assert env["CUDA_VISIBLE_DEVICES"] == "1" and env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert cpu_topology.launch_env(Placement(node_id=0)) is None


def test_run_basement_exe_pinned(monkeypatch):
    calls = []

    class FakePopen:
        pid, returncode = 1, 0

        def __init__(self, command, **kwargs):
            calls.append((command, kwargs.get("env")))

        def communicate(self, timeout=None):
            return "", ""

    monkeypatch.setattr(basement_tools, "basement_validate_paths", lambda paths: None)
    monkeypatch.setattr(basement_tools.subprocess, "Popen", FakePopen)

    basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4})
    assert isinstance(calls[-1][0], list) and calls[-1][1] is None

    placement = Placement(node_id=1, cpus=tuple(range(8, 12)), node_mask=0xF)
    basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4}, placement=placement)
    assert calls[-1][0].startswith('cmd /d /c "start "" /B /WAIT /NODE 1 /AFFINITY 0xf ')
    assert '"--nthreads" "4" & exit"' in calls[-1][0]


def test_queue_places_runs(project, monkeypatch, caplog):  # noqa: F811  (pytest fixture)
    """Parallel queue on 2 x 8 cores with 2 GPUs: no two running simulations share a core or a card."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(cpu_topology, "detect_topology", two_sockets)
    monkeypatch.setattr(cpu_topology, "detect_gpus", lambda override=None: [GpuInfo(0, 0), GpuInfo(1, 1)])
    # Threads instead of processes, so that the fake calculate below is used
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", concurrent.futures.ThreadPoolExecutor)

    lock = threading.Lock()
    running: list[Placement] = []
    seen: list[tuple[bool, Placement]] = []
    clashes: list[tuple[Placement, Placement]] = []  # Failures inside calculate are caught by the queue

    def calculate(sim_config, paths, user_opts, gpu=False, placement=None):
        with lock:
            for other in running:
                shares_card = gpu and other.cuda_device == placement.cuda_device
                if set(other.cpus) & set(placement.cpus) or shares_card:
                    clashes.append((other, placement))
            running.append(placement)
            seen.append((gpu, placement))
        time.sleep(0.05)
        name = Path(sim_config).stem.removesuffix("_model")
        (Path(paths["folder_output"]) / f"{name}_results.h5").write_bytes(b"results")
        with lock:
            running.remove(placement)
        return 0.0

    monkeypatch.setattr(calculate_sim_queue, "calculate", calculate)
    options = {"parallel": True, "overwrite": False, "n_gpus": 2, "n_sim_cpus": 2, "n_sim_threads": 4}
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    calculate_sim_queue.calculate_queue(queue, paths, {"simulation_options": options})

    assert len(seen) == 4 and clashes == []
    assert len(list(Path(paths["folder_output"]).glob("*_results.h5"))) == 4
    for gpu, placement in seen:
        assert placement.pinned
        if gpu:
            assert placement.cuda_device in (0, 1) and len(placement.cpus) == 1
            assert placement.node_id == placement.cuda_device  # the card's own socket
        else:
            assert len(placement.cpus) == 4

    # The log says where each simulation runs
    messages = [record.getMessage() for record in caplog.records]
    assert "CPU sockets: socket 0: 8 cores, socket 1: 8 cores" in messages
    assert "GPUs: GPU 0 on socket 0, GPU 1 on socket 1" in messages
    started = [m for m in messages if " started on " in m]
    assert len(started) == 4
    for message in started:
        gpu_run = re.fullmatch(r"Simulation \w+ started on GPU (\d), socket (\d), CPUs \d+", message)
        cpu_run = re.fullmatch(r"Simulation \w+ started on socket \d, CPUs \d+-\d+", message)
        assert cpu_run or (gpu_run and gpu_run[1] == gpu_run[2]), message


def test_resources_log(monkeypatch, caplog):
    """Messages when pinning is not possible."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(cpu_topology, "detect_topology", lambda: None)
    assert cpu_topology.setup_resources({}, 4, 0).cpu_cores is None
    assert "cannot be read" in caplog.text

    monkeypatch.setattr(cpu_topology, "detect_topology", lambda: two_sockets()[:1])
    assert cpu_topology.setup_resources({}, 4, 0).cpu_cores is None
    assert "Single CPU socket: simulations are not pinned" in caplog.text

    monkeypatch.setattr(cpu_topology, "detect_topology", two_sockets)
    resources = cpu_topology.setup_resources({}, 9, 0)
    assert resources.cpu_cores is None and resources.host_cores is not None
    assert "9 threads do not fit in one CPU socket" in caplog.text


def test_interrupt_kills_basement_tree(monkeypatch):
    """Ctrl+C while BASEMENT runs stops the whole process tree, then the interrupt goes on."""
    killed = []

    class FakePopen:
        pid, returncode = 4321, None

        def __init__(self, command, **kwargs):
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return "", ""

    monkeypatch.setattr(basement_tools, "basement_validate_paths", lambda paths: None)
    monkeypatch.setattr(basement_tools.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(basement_tools.utils, "kill_process_trees", killed.extend)

    with pytest.raises(KeyboardInterrupt):
        basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4})
    assert killed == [4321]


def test_descendants_of_workers():
    """Both workers' BASEMENT trees are found, also when a worker sits under another process."""
    from capiq import utils

    # worker 10 -> cmd 11 -> BMv4_simulation 12 -> solver 13; worker 20 -> BMv4_simulation 21 -> solver 22
    parents = {10: 1, 11: 10, 12: 11, 13: 12, 20: 1, 21: 20, 22: 21, 30: 1}
    assert sorted(utils.descendants([10, 20], parents)) == [10, 11, 12, 13, 20, 21, 22]
    assert utils.descendants([99], parents) == [99]
