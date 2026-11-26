"""Checks socket detection, core and GPU allocation and the pinned launch (no BASEMENT or multi-socket machine needed).

Run from the project root with: pytest tests
"""

import concurrent.futures
import logging
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest
from test_initialization import project  # noqa: F401  (fixture: example project in a temporary folder)

from capiq import basement_tools, calculate_sim_queue, cpu_topology, create_sim_queue, functions_io, utils
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
    assert cpu_topology.parse_nvidia_smi(output) == [(0, (0, 0x41, 0, 0)), (1, (0, 0xC1, 0, 0))]


def test_pinned_command_and_env():
    placement = Placement(node_id=1, cpus=tuple(range(8, 12)), node_mask=0xF, cuda_device=1)
    command = cpu_topology.pinned_command([r"C:\BASEMENT 4\BMv4_simulation.exe", "a b.json"], placement, "win32")
    assert command == (
        'cmd /d /c "start "" /B /WAIT /NODE 1 /AFFINITY 0xf "C:\\BASEMENT 4\\BMv4_simulation.exe" "a b.json" & exit"'
    )
    env = cpu_topology.launch_env(placement)
    assert env["CUDA_VISIBLE_DEVICES"] == "1" and env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert cpu_topology.launch_env(Placement(cuda_device=None)) is None


def test_run_basement_exe_pinned(monkeypatch):
    calls = []

    class FakePopen:
        pid, returncode = 1, 0

        def __init__(self, command, **kwargs):
            calls.append((command, kwargs.get("env")))

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(basement_tools, "basement_validate_paths", lambda paths: None)
    monkeypatch.setattr(basement_tools.subprocess, "Popen", FakePopen)

    basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4})
    assert isinstance(calls[-1][0], list) and calls[-1][1] is None

    placement = Placement(node_id=1, cpus=tuple(range(8, 12)), node_mask=0xF)
    basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4}, placement=placement)
    command = calls[-1][0]
    if sys.platform == "win32":
        assert command.startswith('cmd /d /c "start "" /B /WAIT /NODE 1 /AFFINITY 0xf ')
        assert '"--nthreads" "4" "--progress" & exit"' in command
    else:
        assert command[0] in ("numactl", "taskset") and command[-3:] == ["--nthreads", "4", "--progress"]
    assert f"BMv4_simulation{utils.EXE_SUFFIX}" in str(command)


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

    def calculate(sim_config, paths, user_opts, gpu=False, placement=None, plan=None):
        with lock:
            for other in running:
                shares_card = gpu and other.cuda_device == placement.cuda_device
                if set(other.cpus) & set(placement.cpus) or shares_card:
                    clashes.append((other, placement))
            running.append(placement)
            seen.append((gpu, placement))
        time.sleep(0.05)
        results = calculate_sim_queue.results_file(sim_config, Path(paths["folder_output"]))
        results.parent.mkdir(parents=True, exist_ok=True)
        results.write_bytes(b"results")
        with lock:
            running.remove(placement)
        return 0.0, None

    monkeypatch.setattr(calculate_sim_queue, "calculate", calculate)
    options = {"parallel": True, "overwrite": False, "n_gpus": 2, "n_sim_cpus": 2, "n_sim_threads": 4}
    paths = functions_io.setup_directories()
    queue = create_sim_queue.create_queue(paths)

    calculate_sim_queue.calculate_queue(queue, paths, {"simulation_options": options})

    assert len(seen) == 4 and clashes == []
    assert len(list(Path(paths["folder_output"]).glob("*/*_results.h5"))) == 4
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

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return self.returncode

    monkeypatch.setattr(basement_tools, "basement_validate_paths", lambda paths: None)
    monkeypatch.setattr(basement_tools.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(basement_tools.utils, "kill_process_trees", killed.extend)

    with pytest.raises(KeyboardInterrupt):
        basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4})
    assert killed == [4321]


# ── Linux (fake /sys, so these run on every system) ──────────────────────────


def fake_sys(root: Path, sockets: int, cores_per_socket: int, smt: bool, with_nodes: bool = True) -> Path:
    """A /sys/devices/system tree; with SMT, core c of socket s has CPUs n and n + total cores (Linux numbering)."""
    total = sockets * cores_per_socket
    for s in range(sockets):
        cpus = [s * cores_per_socket + c for c in range(cores_per_socket)]
        node_cpus = cpus + [cpu + total for cpu in cpus] if smt else cpus
        if with_nodes:
            node = root / "node" / f"node{s}"
            node.mkdir(parents=True)
            (node / "cpulist").write_text(",".join(map(str, node_cpus)) + "\n")
        for cpu in cpus:
            siblings = f"{cpu},{cpu + total}" if smt else f"{cpu}"
            for logical in [cpu, cpu + total] if smt else [cpu]:
                topology = root / "cpu" / f"cpu{logical}" / "topology"
                topology.mkdir(parents=True)
                (topology / "thread_siblings_list").write_text(siblings + "\n")
    return root


def test_parse_cpulist():
    assert cpu_topology.parse_cpulist("0-3,8,10-11\n") == [0, 1, 2, 3, 8, 10, 11]
    assert cpu_topology.parse_cpulist("5") == [5]


def test_linux_topology(tmp_path):
    root = fake_sys(tmp_path, sockets=2, cores_per_socket=4, smt=True)
    nodes = cpu_topology.linux_topology(root, allowed=set(range(16)))
    assert [(n.node_id, len(n.cores)) for n in nodes] == [(0, 4), (1, 4)]
    assert nodes[1].cores[0] == (4, 12)  # hyper-thread siblings form one physical core

    # Same allocator as on Windows: one thread per physical core, inside one socket
    placement = CoreAllocator(nodes).acquire(4)
    assert placement.node_id == 0 and placement.cpus == (0, 1, 2, 3)


def test_linux_topology_allowed_cpus_and_no_numa(tmp_path):
    root = fake_sys(tmp_path / "a", sockets=2, cores_per_socket=4, smt=False)
    # A Slurm job or container may use only some CPUs: the others are never pinned
    nodes = cpu_topology.linux_topology(root, allowed={0, 1, 4})
    assert [n.cores for n in nodes] == [((0,), (1,)), ((4,),)]

    # Without NUMA information all CPUs form one socket
    root = fake_sys(tmp_path / "b", sockets=1, cores_per_socket=4, smt=False, with_nodes=False)
    nodes = cpu_topology.linux_topology(root, allowed={0, 1, 2, 3})
    assert len(nodes) == 1 and len(nodes[0].cores) == 4


@pytest.mark.skipif(sys.platform == "win32", reason="PCI folder names contain ':', not allowed in Windows file names")
def test_linux_gpu_numa_node(tmp_path):
    for name, value in [("0000:c1:00.0", "1"), ("0000:41:00.0", "-1")]:
        device = tmp_path / "bus" / "pci" / "devices" / name
        device.mkdir(parents=True)
        (device / "numa_node").write_text(value + "\n")
    assert cpu_topology.linux_gpu_numa_node((0, 0xC1, 0, 0), tmp_path) == 1
    assert cpu_topology.linux_gpu_numa_node((0, 0x41, 0, 0), tmp_path) is None  # -1: unknown
    assert cpu_topology.linux_gpu_numa_node((0, 0x05, 0, 0), tmp_path) is None  # missing


def test_linux_pinned_command(monkeypatch):
    placement = Placement(node_id=1, cpus=(8, 9, 10, 11))
    monkeypatch.setattr(cpu_topology.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    assert cpu_topology.pinned_command(["BMv4_simulation", "a.json"], placement, "linux") == [
        "numactl", "--physcpubind=8-11", "--localalloc", "BMv4_simulation", "a.json"
    ]  # fmt: skip
    monkeypatch.setattr(cpu_topology.shutil, "which", lambda tool: "/usr/bin/taskset" if tool == "taskset" else None)
    assert cpu_topology.pinned_command(["BMv4_simulation"], placement, "linux") == [
        "taskset", "-c", "8-11", "BMv4_simulation"
    ]  # fmt: skip


def test_launch_env_openmp_binding(monkeypatch):
    monkeypatch.delenv("OMP_PROC_BIND", raising=False)
    monkeypatch.setenv("OMP_PLACES", "threads")  # set by the user: kept
    env = cpu_topology.launch_env(Placement(node_id=0, cpus=(0,)))
    assert env["OMP_PROC_BIND"] == "close" and env["OMP_PLACES"] == "threads"
    assert "CUDA_VISIBLE_DEVICES" not in env


def test_exe_suffix():
    assert utils.EXE_SUFFIX == (".exe" if sys.platform == "win32" else "")


# ── Real operating system (run in CI on Linux and Windows) ──────────────────


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS cannot pin processes to cores")
@pytest.mark.parametrize("tool", ["numactl", "taskset"])
def test_pinned_launch_real(tool, monkeypatch):
    """A program started through pinned_command runs on the requested CPU only."""
    if sys.platform == "win32":
        if tool == "taskset":
            pytest.skip("one launcher on Windows")
    elif shutil.which(tool) is None:
        pytest.skip(f"{tool} not installed")
    else:
        which = shutil.which  # the original: cpu_topology.shutil is this same module
        monkeypatch.setattr(cpu_topology.shutil, "which", lambda name: which(name) if name == tool else None)

    placement = Placement(node_id=0, cpus=(0,), node_mask=0b1)
    program = [sys.executable, "-c", "import psutil; print(psutil.Process().cpu_affinity())"]
    command = cpu_topology.pinned_command(program, placement)
    completed = subprocess.run(
        command, capture_output=True, text=True, env=cpu_topology.launch_env(placement), timeout=60
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[0]"


def alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_kill_process_trees_real():
    """A process and the process it started are both stopped (as BMv4_simulation and its solver)."""
    child = "import time; time.sleep(60)"
    parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); print('ready', flush=True); time.sleep(60)"
    root = subprocess.Popen([sys.executable, "-c", parent], stdout=subprocess.PIPE, text=True)
    assert root.stdout.readline().strip() == "ready"
    tree = [root.pid, *(p.pid for p in psutil.Process(root.pid).children(recursive=True))]
    assert len(tree) >= 2

    utils.kill_process_trees([root.pid])
    root.wait(timeout=10)
    assert not [pid for pid in tree if alive(pid)]


def test_worker_logging_reaches_main_log(caplog):
    """Records logged in real worker processes reach the main process's log once, at its level."""
    caplog.set_level("INFO")

    with utils.worker_logging() as (initializer, initargs):
        with concurrent.futures.ProcessPoolExecutor(max_workers=2, initializer=initializer, initargs=initargs) as pool:
            futures = [pool.submit(logging.warning, "from worker %d", i) for i in range(4)]
            futures.append(pool.submit(logging.debug, "below the log level"))
            for future in futures:
                future.result()

    # Also the records still in the queue when the pool finished were written out
    for i in range(4):
        assert caplog.text.count(f"from worker {i}") == 1
    assert "below the log level" not in caplog.text


def test_worker_logging_in_main_process_keeps_handlers():
    """In the main process (a thread pool), the initializer leaves the log handlers alone."""
    handlers = list(logging.getLogger().handlers)
    with utils.worker_logging() as (initializer, initargs):
        initializer(*initargs)
    assert logging.getLogger().handlers == handlers


def test_basement_log(tmp_path, monkeypatch):
    """BASEMENT writes into the log file while it runs, also when the program fails."""
    outputs = iter([(0, b"simulation finished at t = 10 (cpu-time = 1s)\n"), (3, b"reading mesh\nError: bad mesh\n")])
    log = tmp_path / "X_run.log"
    seen_at_start = []

    class FakePopen:
        pid = 1

        def __init__(self, command, stdout=None, stderr=None, **kwargs):
            assert stderr == subprocess.STDOUT  # both streams go to the log, in order
            seen_at_start.append(log.read_text(encoding="utf-8"))
            self.returncode, out = next(outputs)
            stdout.write(out)  # the program writes to the log file itself

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(basement_tools, "basement_validate_paths", lambda paths: None)
    monkeypatch.setattr(basement_tools.subprocess, "Popen", FakePopen)

    output = basement_tools.run_simulation(
        "run.json", "setup.h5", "results.h5", {"n_sim_threads": 4}, log_filepath=str(log)
    )
    assert "simulation finished at t = 10" in output["stdout"]  # read back for the RTS statistics
    with pytest.raises(Exception, match="X_run.log"):
        basement_tools.run_results("results.json", "results.h5", "results.xdmf", log_filepath=str(log))

    # The command is in the log before the program starts
    assert "BMv4_simulation" in seen_at_start[0] and "return code" not in seen_at_start[0]
    text = log.read_text(encoding="utf-8")
    assert "BMv4_simulation" in text and "return code 0" in text and "simulation finished at t = 10" in text
    assert "BMv4_results" in text and "return code 3" in text and "Error: bad mesh" in text
    assert text.index("Error: bad mesh") < text.index("return code 3")


def test_basement_log_is_written_live(tmp_path, monkeypatch):
    """A real program's output is in the log file before the program ends."""
    script = tmp_path / "program.py"
    script.write_text("import sys, time\nprint('first', flush=True)\ntime.sleep(3)\nprint('second')\n")
    log = tmp_path / "X_run.log"
    monkeypatch.setattr(basement_tools.c, "BASEMENT_PATH", str(Path(sys.executable).parent))

    runner = threading.Thread(
        target=basement_tools.run_basement_exe,
        kwargs={"exe_name": Path(sys.executable).name, "input_files": [str(script)], "log_filepath": str(log)},
    )

    def read_log() -> str:
        return log.read_text(encoding="utf-8") if log.exists() else ""

    runner.start()
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline and "first" not in read_log():
        time.sleep(0.05)
    text_while_running = read_log()
    runner.join(timeout=30)

    assert "first" in text_while_running and "second" not in text_while_running
    text = log.read_text(encoding="utf-8")
    assert "second" in text and "return code 0" in text


def test_basement_output_without_log(monkeypatch):
    """Without a log file the output is still returned."""

    class FakePopen:
        pid, returncode = 1, 0

        def __init__(self, command, stdout=None, **kwargs):
            stdout.write(b"done\n")

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(basement_tools, "basement_validate_paths", lambda paths: None)
    monkeypatch.setattr(basement_tools.subprocess, "Popen", FakePopen)
    output = basement_tools.run_simulation("run.json", "setup.h5", "results.h5", {"n_sim_threads": 4})
    assert output["stdout"] == "done\n" and output["returncode"] == 0
