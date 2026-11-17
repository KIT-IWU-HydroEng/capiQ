#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

"""
Places simulations on CPU sockets (NUMA nodes) and GPUs.

On a machine with several sockets, a simulation whose threads spread over two sockets pays for
every memory access that crosses the link between them. This module detects the sockets and
their physical cores (Windows only), hands out disjoint sets of cores inside one socket, and
launches BASEMENT pinned to them with Windows' own ``start /NODE /AFFINITY``. GPU runs get a
free card (``CUDA_VISIBLE_DEVICES``) and one core on the socket the card is attached to.

Check what is detected on a machine with:
    uv run python -c "from capiq import cpu_topology; cpu_topology.report()"
"""

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Import libraries
import json
import logging
import os
import re
import struct
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

logger = logging.getLogger("cpu_topology")

# LOGICAL_PROCESSOR_RELATIONSHIP values
_RELATION_PROCESSOR_CORE = 0
_RELATION_NUMA_NODE = 1

# Byte offset of the first GROUP_AFFINITY in PROCESSOR_RELATIONSHIP and NUMA_NODE_RELATIONSHIP
_GROUP_COUNT_OFFSET = 22
_GROUP_MASK_OFFSET = 24
_GROUP_AFFINITY_SIZE = 16


@dataclass(frozen=True)
class NumaNode:
    """One CPU socket (NUMA node) inside one processor group."""

    node_id: int
    group: int
    mask: int  # Logical CPUs of the node, as bits within the processor group
    cores: tuple[tuple[int, ...], ...]  # Logical CPUs (group numbering) of each physical core

    @property
    def base(self) -> int:
        """Lowest logical CPU of the node: bit 0 of the masks given to ``start /NODE``."""
        return (self.mask & -self.mask).bit_length() - 1


@dataclass(frozen=True)
class GpuInfo:
    """A GPU card and the socket it is attached to (None if unknown)."""

    index: int | None  # nvidia-smi index (PCI bus order); None if no card was detected
    numa_node: int | None = None


@dataclass(frozen=True)
class Placement:
    """Where one simulation runs: a set of cores in one socket and/or a GPU card."""

    node_id: int | None = None
    cpus: tuple[int, ...] = ()  # Logical CPUs, group numbering
    node_mask: int = 0  # Same CPUs as bits relative to the node's lowest CPU (for start /AFFINITY)
    cuda_device: int | None = None
    core_ids: tuple[int, ...] = field(default=(), repr=False)  # Indices into NumaNode.cores

    @property
    def pinned(self) -> bool:
        return self.node_id is not None

    def describe(self) -> str:
        parts = []
        if self.cuda_device is not None:
            parts.append(f"GPU {self.cuda_device}")
        if self.pinned:
            parts.append(f"socket {self.node_id}, CPUs {_ranges(self.cpus)}")
        return ", ".join(parts) or "unpinned"


def _ranges(values: tuple[int, ...]) -> str:
    """Compacts (0, 1, 2, 4, 6, 7) into "0-2,4,6-7"."""
    spans: list[list[int]] = []
    for v in sorted(values):
        if spans and spans[-1][1] == v - 1:
            spans[-1][1] = v
        else:
            spans.append([v, v])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in spans)


def _bits(mask: int) -> tuple[int, ...]:
    return tuple(i for i in range(mask.bit_length()) if mask >> i & 1)


# ── Topology detection ───────────────────────────────────────────────────────


def _records(raw: bytes) -> Iterator[tuple[int, bytes]]:
    """Splits a SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX buffer into (relationship, body)."""
    offset = 0
    while offset + 8 <= len(raw):
        relationship, size = struct.unpack_from("<II", raw, offset)
        if size < 8:
            break
        yield relationship, raw[offset + 8 : offset + size]
        offset += size


def _group_masks(body: bytes) -> list[tuple[int, int]]:
    """(mask, group) of each GROUP_AFFINITY in a processor or NUMA node record."""
    count = struct.unpack_from("<H", body, _GROUP_COUNT_OFFSET)[0] or 1  # Older Windows: reserved (0)
    offsets = (_GROUP_MASK_OFFSET + _GROUP_AFFINITY_SIZE * i for i in range(count))
    # Each entry needs its Mask (8 bytes) and Group (2 bytes)
    return [struct.unpack_from("<QH", body, offset) for offset in offsets if offset + 10 <= len(body)]


def parse_topology(numa_raw: bytes, core_raw: bytes) -> list[NumaNode]:
    """
    Builds the socket list from the raw GetLogicalProcessorInformationEx buffers.

    Args:
        numa_raw: Buffer returned for RelationNumaNode.
        core_raw: Buffer returned for RelationProcessorCore.

    Returns:
        One NumaNode per socket, sorted by node number. A node spanning several processor
        groups (more than 64 logical CPUs) keeps only its first group.
    """
    node_masks: dict[int, tuple[int, int]] = {}
    for relationship, body in _records(numa_raw):
        if relationship != _RELATION_NUMA_NODE:
            continue
        node_id = struct.unpack_from("<I", body, 0)[0]
        masks = _group_masks(body)
        if len(masks) > 1:
            logger.warning(f"NUMA node {node_id} spans {len(masks)} processor groups; only group {masks[0][1]} is used")
        node_masks.setdefault(node_id, masks[0])

    cores: dict[int, list[tuple[int, ...]]] = {node_id: [] for node_id in node_masks}
    for relationship, body in _records(core_raw):
        if relationship != _RELATION_PROCESSOR_CORE:
            continue
        mask, group = _group_masks(body)[0]
        for node_id, (node_mask, node_group) in node_masks.items():
            if node_group == group and mask & node_mask == mask:
                cores[node_id].append(_bits(mask))
                break

    return [
        NumaNode(node_id, group, mask, tuple(sorted(cores[node_id])))
        for node_id, (mask, group) in sorted(node_masks.items())
    ]


def _query_processor_information(relationship: int) -> bytes:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    func = kernel32.GetLogicalProcessorInformationEx
    func.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    func.restype = wintypes.BOOL

    length = wintypes.DWORD(0)
    func(relationship, None, ctypes.byref(length))
    buffer = ctypes.create_string_buffer(length.value)
    if not func(relationship, buffer, ctypes.byref(length)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.raw[: length.value]


def detect_topology() -> list[NumaNode] | None:
    """Returns the sockets of this machine, or None where they cannot be read (non-Windows)."""
    if sys.platform != "win32":
        return None
    try:
        nodes = parse_topology(
            _query_processor_information(_RELATION_NUMA_NODE),
            _query_processor_information(_RELATION_PROCESSOR_CORE),
        )
    except (OSError, struct.error) as exc:
        logger.warning(f"Could not read the CPU topology: {exc}")
        return None
    return [node for node in nodes if node.cores] or None


# ── GPU detection ────────────────────────────────────────────────────────────


def parse_nvidia_smi(output: str) -> list[tuple[int, tuple[int, int, int]]]:
    """Parses "index, 00000000:41:00.0" lines into (index, (bus, device, function))."""
    gpus = []
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s*,\s*(?:[0-9A-Fa-f]+:)?([0-9A-Fa-f]+):([0-9A-Fa-f]+)\.([0-9A-Fa-f]+)", line)
        if match:
            index, bus, device, function = match.groups()
            gpus.append((int(index), (int(bus, 16), int(device, 16), int(function, 16))))
    return gpus


def parse_pnp_numa(data: list | dict) -> dict[tuple[int, int, int], int]:
    """
    {(bus, device, function): NUMA node} from the PnP properties of the display adapters.

    Uses the numeric bus number and address (device << 16 | function) rather than the
    "PCI bus 3, device 0, function 0" text, which is translated with the Windows language.
    """
    result = {}
    for item in [data] if isinstance(data, dict) else data:
        bus, address, numa = item.get("bus"), item.get("address"), item.get("numa")
        if isinstance(bus, int) and isinstance(address, int) and isinstance(numa, int) and 0 <= numa < 64:
            result[(bus, address >> 16, address & 0xFFFF)] = numa
    return result


def _gpu_numa_nodes() -> dict[tuple[int, int, int], int]:
    """{(bus, device, function): NUMA node} of the display adapters, read from Windows' device properties."""
    script = (
        "Get-PnpDevice -Class Display -PresentOnly | ForEach-Object { "
        "$p = $_ | Get-PnpDeviceProperty -KeyName DEVPKEY_Device_BusNumber,DEVPKEY_Device_Address,DEVPKEY_Device_Numa_Node; "
        "[pscustomobject]@{ bus = $p[0].Data; address = $p[1].Data; numa = $p[2].Data } } | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
        return parse_pnp_numa(json.loads(completed.stdout or "[]"))
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError) as exc:
        logger.warning(f"Could not read the GPU sockets: {exc}")
        return {}


def detect_gpus(numa_override: list[int] | None = None) -> list[GpuInfo] | None:
    """
    Lists the NVIDIA cards with the socket each one is attached to.

    Args:
        numa_override: Socket of each card by nvidia-smi index; wins over detection.

    Returns:
        The cards in nvidia-smi order, or None if nvidia-smi is not available.
    """
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,pci.bus_id", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    cards = parse_nvidia_smi(completed.stdout)
    if not cards:
        return None

    detected = _gpu_numa_nodes() if sys.platform == "win32" and not numa_override else {}
    gpus = []
    for index, location in cards:
        if numa_override and index < len(numa_override):
            gpus.append(GpuInfo(index, int(numa_override[index])))
        else:
            gpus.append(GpuInfo(index, detected.get(location)))
    return gpus


# ── Allocation ───────────────────────────────────────────────────────────────


class CoreAllocator:
    """Hands out disjoint sets of cores, each inside one socket."""

    def __init__(self, nodes: list[NumaNode], physical_only: bool = True):
        self.nodes = {node.node_id: node for node in nodes}
        self.physical_only = physical_only
        self._free = {node.node_id: set(range(len(node.cores))) for node in nodes}

    def _cores_needed(self, node: NumaNode, cores: list[int], n_threads: int) -> list[int] | None:
        """First cores (from `cores`) that give n_threads threads, or None if they are not enough."""
        taken, threads = [], 0
        for core in cores:
            if threads >= n_threads:
                break
            taken.append(core)
            threads += 1 if self.physical_only else len(node.cores[core])
        return taken if threads >= n_threads else None

    def free_cores(self, node_id: int | None) -> int:
        """Number of free cores in a socket (0 for an unknown socket)."""
        return len(self._free.get(node_id, ())) if node_id is not None else 0

    def fits(self, n_threads: int) -> bool:
        """Whether a run of n_threads fits inside one socket at all."""
        return any(
            self._cores_needed(node, list(range(len(node.cores))), n_threads) is not None
            for node in self.nodes.values()
        )

    def acquire(self, n_threads: int, node_id: int | None = None) -> Placement | None:
        """
        Reserves cores for a run of n_threads inside one socket.

        The socket with the most free cores is chosen, so runs spread over the sockets and
        each one gets as much memory bandwidth as possible.

        Args:
            n_threads: Threads of the run.
            node_id: Socket to use; any socket if None.

        Returns:
            The placement, or None if no socket has enough free cores now.
        """
        candidates = [self.nodes[node_id]] if node_id is not None else list(self.nodes.values())
        best = None
        for node in candidates:
            taken = self._cores_needed(node, sorted(self._free[node.node_id]), n_threads)
            if taken is None:
                continue
            if best is None or len(self._free[node.node_id]) > len(self._free[best[0].node_id]):
                best = (node, taken)
        if best is None:
            return None

        node, taken = best
        self._free[node.node_id].difference_update(taken)
        if self.physical_only:
            cpus = tuple(node.cores[core][0] for core in taken)
        else:
            cpus = tuple(cpu for core in taken for cpu in node.cores[core])
        node_mask = sum(1 << (cpu - node.base) for cpu in cpus)
        return Placement(node.node_id, cpus, node_mask, None, tuple(taken))

    def release(self, placement: Placement | None) -> None:
        if placement is not None and placement.node_id in self._free:
            self._free[placement.node_id].update(placement.core_ids)


class GpuSlots:
    """GPU workers, spread round-robin over the detected cards (several workers may share a card)."""

    def __init__(self, gpus: list[GpuInfo] | None, n_slots: int):
        if gpus:
            self.slots = [gpus[i % len(gpus)] for i in range(n_slots)]
        else:
            self.slots = [GpuInfo(None) for _ in range(n_slots)]
        self.busy: set[int] = set()

    def free(self) -> bool:
        return len(self.busy) < len(self.slots)

    def acquire(self, cores: CoreAllocator | None) -> tuple[int, Placement]:
        """
        Takes a free GPU worker, preferring a card whose socket still has a free core, then the least busy card.

        The run also gets one core on the card's socket for the host thread that drives it,
        if pinning is on and the socket is known.

        Returns:
            (slot, placement); release both with `release` and `CoreAllocator.release`.
        """

        def has_core(slot: int) -> bool:
            return cores is not None and cores.free_cores(self.slots[slot].numa_node) > 0

        def load(slot: int) -> int:
            return sum(1 for busy in self.busy if self.slots[busy].index == self.slots[slot].index)

        free_slots = [slot for slot in range(len(self.slots)) if slot not in self.busy]
        slot = min(free_slots, key=lambda s: (not has_core(s), load(s), s))
        self.busy.add(slot)

        gpu = self.slots[slot]
        placement = Placement()
        if cores is not None and has_core(slot):
            placement = cores.acquire(1, gpu.numa_node) or placement
        return slot, replace(placement, cuda_device=gpu.index)

    def release(self, slot: int) -> None:
        self.busy.discard(slot)


# ── Launch ───────────────────────────────────────────────────────────────────


def pinned_command(cmd: list[str], placement: Placement) -> str:
    """
    Wraps a command so that Windows starts it on the placement's socket and cores.

    ``start /NODE`` also places the process's memory on that socket and works across processor
    groups. ``& exit`` hands the exit code of the program back to the caller (``start /WAIT``
    alone does not).
    """
    program = " ".join(f'"{arg}"' for arg in cmd)
    return (
        f'cmd /d /c "start "" /B /WAIT /NODE {placement.node_id} /AFFINITY {placement.node_mask:#x} {program} & exit"'
    )


def launch_env(placement: Placement | None) -> dict[str, str] | None:
    """Environment of the child process: selects the GPU card, None to inherit unchanged."""
    if placement is None or placement.cuda_device is None:
        return None
    return {**os.environ, "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": str(placement.cuda_device)}


@dataclass
class Resources:
    """What the queue uses to place runs."""

    cpu_cores: CoreAllocator | None  # Pins CPU runs; None: CPU runs are not pinned
    host_cores: CoreAllocator | None  # Pins the host thread of GPU runs (same allocator, so cores are shared)
    gpus: GpuSlots | None  # GPU workers; None without GPU workers


def setup_resources(sim_opts: dict, n_threads: int, n_gpu: int) -> Resources:
    """
    Detects sockets and GPUs and prepares the allocators, following the user options.

    Args:
        sim_opts: "simulation_options" of the user options.
        n_threads: Threads of each CPU run.
        n_gpu: Number of GPU workers.
    """
    cores = None
    if sim_opts.get("pin_to_socket", True):
        nodes = detect_topology()
        if nodes is None:
            logger.info(f"CPU sockets cannot be read on {sys.platform} (Windows only): simulations are not pinned")
        elif len(nodes) < 2:
            logger.info("Single CPU socket: simulations are not pinned")
        else:
            cores = CoreAllocator(nodes, sim_opts.get("physical_cores_only", True))
            summary = ", ".join(f"socket {n.node_id}: {len(n.cores)} cores" for n in nodes)
            logger.info(f"CPU sockets: {summary}")

    cpu_cores = cores
    if cores is not None and not cores.fits(n_threads):
        logger.warning(f"{n_threads} threads do not fit in one CPU socket: CPU simulations are not pinned")
        cpu_cores = None

    gpus = None
    if n_gpu > 0:
        detected = detect_gpus(sim_opts.get("gpu_numa_nodes"))
        if detected is None:
            logger.warning("nvidia-smi not found: the GPU card of each GPU simulation is left to BASEMENT")
        else:
            cards = ", ".join(f"GPU {g.index} on socket {g.numa_node}" for g in detected)
            logger.info(f"GPUs: {cards}")
            if n_gpu > len(detected):
                logger.warning(f"{n_gpu} GPU workers on {len(detected)} card(s): some cards run several simulations")
        gpus = GpuSlots(detected, n_gpu)

    return Resources(cpu_cores, cores, gpus)


def report(basement_path: str | None = None) -> None:
    """Prints what was detected on this machine (sockets, cores, GPUs, BASEMENT's OpenMP runtime)."""
    nodes = detect_topology()
    if nodes is None:
        print("CPU topology: not available")
    else:
        for node in nodes:
            smt = max(len(core) for core in node.cores)
            print(
                f"socket {node.node_id}: group {node.group}, {len(node.cores)} physical cores, "
                f"{smt} thread(s) per core, logical CPUs {_ranges(_bits(node.mask))}"
            )
        print(f"Pinning: {'on' if len(nodes) > 1 else 'off (single socket)'}")

    gpus = detect_gpus()
    if gpus is None:
        print("GPUs: nvidia-smi not found")
    for gpu in gpus or []:
        print(f"GPU {gpu.index}: socket {gpu.numa_node if gpu.numa_node is not None else 'unknown'}")

    if basement_path is None:
        try:
            from user_defined import constants

            basement_path = constants.BASEMENT_PATH
        except ImportError:
            basement_path = r"C:\Program Files\BASEMENT 4.3.0\bin"
    # OpenMP runtime imported by the OpenMP backend: MSVC's vcomp ignores OMP_PROC_BIND / OMP_PLACES
    backend = Path(basement_path) / "BMv4_BASEHPC_omp.exe"
    try:
        found = re.findall(rb"(?i)(vcomp\w*|libiomp\w*|libomp\w*|libgomp[-\w]*)\.dll", backend.read_bytes())
        runtimes = sorted({name.decode().lower() + ".dll" for name in found})
        print(f"OpenMP runtime of {backend.name}: {', '.join(runtimes) or 'none found'}")
    except OSError:
        print(f"OpenMP runtime: {backend} not found")
