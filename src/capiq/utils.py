#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Libraries
import sys
import time

import psutil

# BASEMENT executables are named BMv4_*.exe on Windows and BMv4_* on Linux
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""
# Default BASEMENT installation folder (Linux: the .deb package installs to /usr/bin)
DEFAULT_BASEMENT_PATH = r"C:\Program Files\BASEMENT 4.3.0\bin" if sys.platform == "win32" else "/usr/bin"


def timeit(
    logger,
    message_start: str | None = None,
    message_end: str | None = None,
):
    """
    Decorator to log function execution time.

    Args:
        logger: The logger to use.
        message_start: Optional custom message logged at the start.
                       Can include {func_name} as a placeholder.
        message_end: Optional custom message logged at the end.
                     Can include {func_name} and {elapsed} as placeholders.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.time()
            func_name = func.__name__

            if message_start:
                logger.info(message_start.format(func_name=func_name))
            else:
                logger.info(f"Starting: {func_name}")

            result = func(*args, **kwargs)

            elapsed = time.time() - start

            if message_end:
                logger.info(message_end.format(func_name=func_name, elapsed=elapsed))
            else:
                logger.info(f"Finished: {func_name}")
                logger.info(f"Function executed in {elapsed:.4f} seconds")

            return result

        return wrapper

    return decorator


def format_duration(seconds: float) -> str:
    """Formats a duration as "01d 02h 03min 04s" (whole seconds)."""
    minutes, secs = divmod(int(seconds), 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    return f"{days:02d}d {hours:02d}h {minutes:02d}min {secs:02d}s"


def kill_process_trees(pids: list[int]) -> None:
    """
    Kills processes and all the processes they started.

    BASEMENT's BMv4_simulation starts the actual solver (BMv4_BASEHPC_*) as a child, and pinned
    runs add a launcher in front (cmd.exe, numactl or taskset), so stopping only the direct child
    leaves the solver running. The whole tree is read first and then killed: once a process is
    gone, its children can no longer be found.

    Args:
        pids: Process ids of the tops of the trees.
    """
    processes: list[psutil.Process] = []
    for pid in pids:
        try:
            root = psutil.Process(pid)
            processes += [root, *root.children(recursive=True)]
        except psutil.NoSuchProcess:
            pass

    for process in processes:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(processes, timeout=5)
