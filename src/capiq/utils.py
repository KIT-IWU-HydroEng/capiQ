#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Libraries
import os
import signal
import subprocess
import sys
import time


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


def _windows_parent_pids() -> dict[int, int]:
    """{process id: parent process id} of every running process (Windows)."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return {}
    parents = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return parents


def descendants(roots: list[int], parents: dict[int, int]) -> list[int]:
    """The roots and every process below them, from a {pid: parent pid} snapshot."""
    found = list(dict.fromkeys(roots))
    for pid in found:  # grows while iterating: breadth-first walk
        found.extend(child for child, parent in parents.items() if parent == pid and child not in found)
    return found


def kill_process_trees(pids: list[int]) -> None:
    """
    Kills processes and all the processes they started.

    BASEMENT's BMv4_simulation.exe starts the actual solver (BMv4_BASEHPC_*.exe) as a child,
    and pinned runs add cmd.exe in front, so stopping only the direct child leaves the solver running.
    The whole tree is read first and then killed at once: once a process is gone, its children
    can no longer be found.

    Args:
        pids: Process ids of the tops of the trees.
    """
    if not pids:
        return
    if sys.platform == "win32":
        tree = descendants(pids, _windows_parent_pids())
        args = [arg for pid in tree for arg in ("/PID", str(pid))]
        subprocess.run(["taskkill", "/F", *args], capture_output=True)
    else:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
