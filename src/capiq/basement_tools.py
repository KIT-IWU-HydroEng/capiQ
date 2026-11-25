#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Import libraries
import json
import locale
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import IO

from capiq import utils
from capiq.cpu_topology import Placement, launch_env, pinned_command
from user_defined import constants as c

# Create a logger for basement_tools
logger = logging.getLogger("basement_tools")


def mesh_name_from_json(filepath: str) -> str:
    """
    Extracts the mesh name from the JSON file.

    Parameters:
        filepath (str): Path to the JSON file.

    Returns:
        str: The mesh name extracted from the JSON file.
    """
    with open(filepath) as file:
        data = json.load(file)
        mesh_name: str = data["SETUP"]["BASEHPC"]["BASEPLANE_2D"]["GEOMETRY"]["mesh_file"]

    return mesh_name


def _file_values(obj) -> list[str]:
    """Return every string value whose key contains "file" in a nested dict/list."""
    values = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                values.extend(_file_values(value))
            elif "file" in key.lower() and isinstance(value, str):
                values.append(value)
    elif isinstance(obj, list):
        for item in obj:
            values.extend(_file_values(item))
    return values


def initialization_files_from_json(filepath: str) -> list[str]:
    """
    Extracts the initialization file names required by a model JSON file.

    Looks at the "file" keys of HYDRAULICS.INITIAL and HYDRAULICS.TURBULENCE.INITIAL,
    the same sections handled by ``model_update_filepaths``.

    Parameters:
        filepath (str): Path to the model JSON file.

    Returns:
        list[str]: Unique base names of the required initialization files.
    """
    with open(filepath) as file:
        data = json.load(file)

    hydraulics = data["SETUP"]["BASEHPC"]["BASEPLANE_2D"]["HYDRAULICS"]
    values = _file_values(hydraulics.get("INITIAL", {}))
    values += _file_values(hydraulics.get("TURBULENCE", {}).get("INITIAL", {}))

    return list(dict.fromkeys(os.path.basename(value) for value in values))


def basement_validate_paths(
    paths: list,
    error_message: str | None = None,
) -> None:
    """
    Validate the existence of required file paths.

    Parameters:
        paths (List[str]): A list of file paths to validate.
        error_message (Optional[str]): A custom error message to log if validation fails.

    Raises:
        FileNotFoundError: If a path does not exist.
    """
    invalid_paths = [path for path in paths if not os.path.exists(path)]
    if invalid_paths:
        error_message = error_message or "One or more required paths are invalid."
        raise FileNotFoundError(f"{error_message} {invalid_paths}")


def _open_output(log_filepath: str | None) -> IO[bytes]:
    """
    File BASEMENT's output is written to while it runs: the log file (appended to),
    or a temporary file if there is no log or it cannot be opened.
    """
    if log_filepath:
        try:
            file = open(log_filepath, "a+b")  # Writes always go to the end, reads from the position
            file.seek(0, os.SEEK_END)
            return file
        except OSError as exc:
            logger.warning(f"Could not write the BASEMENT log {log_filepath}: {exc}")
    return tempfile.TemporaryFile()


def _write_line(file: IO[bytes], text: str) -> None:
    file.write(f"{text}\n".encode())
    file.flush()


def run_basement_exe(
    exe_name: str,
    input_files: list[str] | None = None,
    output_filepath: str | None = None,
    run_options: dict | None = None,
    extra_args: list[str] | None = None,
    placement: Placement | None = None,
    log_filepath: str | None = None,
) -> dict[str, str | int]:
    """
    Execute a BASEMENT executable and capture its output.

    Args:
        exe_name          : Name of the BASEMENT executable
                            (e.g. ``"BMv4_setup.exe"`` on Windows, ``"BMv4_setup"`` on Linux).
        input_files       : List of input file paths (e.g. config files).
        output_filepath   : Path for the output file.
        run_options       : Optional dict with keys like
                             ``verbose`` (bool) and ``basement_path`` (str).
        extra_args        : Additional command-line arguments
                            (e.g. ``["--backend", "omp", "--nthreads", "4"]``).
        placement         : Optional CPU socket, cores and GPU card to run on
                            (see ``capiq.cpu_topology``). None runs unpinned.
        log_filepath      : Optional text file the command and BASEMENT's output are
                            appended to while the program runs (also when it fails).

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
        BASEMENT's stdout and stderr go to the file together, so ``stdout`` holds both
        (in the order they were written) and ``stderr`` is empty.
    """
    if run_options is None:
        run_options = {}

    # Resolve BASEMENT installation path
    basement_path = c.BASEMENT_PATH or run_options.get("basement_path", utils.DEFAULT_BASEMENT_PATH)
    exe_path = os.path.join(basement_path, exe_name)

    # Validate paths before running
    all_required = [exe_path]
    if input_files:
        all_required.extend(input_files)
    basement_validate_paths(all_required)

    # Build the command as a list (avoids quoting headaches)
    cmd = [exe_path]
    if input_files:
        cmd.extend(input_files)
    if output_filepath:
        cmd.extend(["--output", output_filepath])
    if extra_args:
        cmd.extend(extra_args)

    # Pin to a CPU socket and select the GPU card, if a placement is given
    command: str | list[str] = cmd
    if placement is not None and placement.pinned:
        command = pinned_command(cmd, placement)

    # BASEMENT writes its output straight into the log file, so the log grows while it runs
    with _open_output(log_filepath) as output:
        _write_line(output, f"===== {' '.join(cmd)}")
        start = output.tell()
        try:
            process = subprocess.Popen(
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=launch_env(placement),
            )
        except OSError as exc:
            _write_line(output, f"===== could not start: {exc}\n")
            logging.error(f"Unable to start {exe_path!r}: {exc}")
            raise

        try:
            # Short waits: on Windows, Ctrl+C is not seen during a wait without timeout
            while True:
                try:
                    process.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            # Ctrl+C or shutdown: stop BASEMENT with its solver process, not only the direct child
            utils.kill_process_trees([process.pid])
            try:
                process.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                pass
            _write_line(output, "===== interrupted\n")
            raise

        # Read back what BASEMENT wrote (for the RTS statistics and the error messages)
        output.seek(start)
        text = output.read().decode(locale.getpreferredencoding(False), errors="replace")
        output.seek(0, os.SEEK_END)
        _write_line(output, f"===== return code {process.returncode}\n")

    completed = subprocess.CompletedProcess(cmd, process.returncode, text, "")

    # Optional verbose logging (useful when you run manually)
    if run_options.get("verbose"):
        if completed.stdout:
            logging.info("--- STDOUT ---")
            logging.info(completed.stdout)
        if completed.stderr:
            logging.error("--- STDERR ---")
            logging.error(completed.stderr)

    # Always log the full output on failure
    if completed.returncode != 0:
        where = f" on {placement.describe()}" if placement is not None else ""
        logging.error(f"'{exe_name}' failed (return code {completed.returncode}){where}. Command: {' '.join(cmd)}")
        if completed.stderr:
            logging.error("--- STDERR ---")
            logging.error(completed.stderr)
        if completed.stdout:
            logging.info("--- STDOUT (extra info) ---")
            logging.info(completed.stdout)

        see = f" and {log_filepath}" if log_filepath else ""
        raise Exception(f"{exe_name} failed. Check the log{see} for details.")

    # Hand the captured output back to the caller
    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }


def run_setup(
    config_filepath: str,
    setup_filepath: str,
    run_options: dict | None = None,
    placement: Placement | None = None,
    log_filepath: str | None = None,
) -> dict[str, str | int]:
    """
    Execute the BASEMENT setup process.

    Args:
        config_filepath : Path to the simulation configuration file.
        setup_filepath  : Path where the generated setup file will be written.
        run_options     : Optional dict with keys like
                           ``verbose`` (bool) and ``basement_path`` (str).
        placement       : Optional CPU socket, cores and GPU card to run on.
        log_filepath    : Optional text file BASEMENT's output is appended to.

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
    """
    return run_basement_exe(
        exe_name=f"BMv4_setup{utils.EXE_SUFFIX}",
        input_files=[config_filepath],
        output_filepath=setup_filepath,
        run_options=run_options,
        placement=placement,
        log_filepath=log_filepath,
    )


def run_simulation(
    run_config_filepath: str,
    setup_filepath: str,
    results_filepath: str,
    run_options: dict | None = None,
    override_backend: str | None = None,
    placement: Placement | None = None,
    log_filepath: str | None = None,
) -> dict[str, str | int]:
    """
    Execute a BASEMENT simulation.

    Args:
        run_config_filepath : Path to the simulation configuration file.
        setup_filepath      : Path to the setup file generated by BASEMENT.
        results_filepath    : Path to the output results file.
        run_options         : Optional dict with keys like
                               ``verbose`` (bool), ``basement_path`` (str),
                               ``backend`` (str), and ``nthreads`` (int).
        override_backend    : Optional backend override. Default is 'omp'.
        placement           : Optional CPU socket, cores and GPU card to run on.
        log_filepath        : Optional text file BASEMENT's output is appended to.

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
    """
    if run_options is None:
        run_options = {}

    backend = run_options.get("backend", "omp")
    if override_backend is not None:
        backend = override_backend

    if backend in ("cuda", "cudaC"):
        nthreads = 1

    else:
        nthreads = run_options.get("n_sim_threads", os.cpu_count() or 1)

    return run_basement_exe(
        exe_name=f"BMv4_simulation{utils.EXE_SUFFIX}",
        input_files=[run_config_filepath, setup_filepath],
        output_filepath=results_filepath,
        run_options=run_options,
        # --progress: progress lines with the real-time speedup, kept in the BASEMENT log
        extra_args=["--backend", backend, "--nthreads", str(nthreads), "--progress"],
        placement=placement,
        log_filepath=log_filepath,
    )


def run_results(
    results_config_file: str,
    results_filepath: str,
    results_output_file: str,
    run_options: dict | None = None,
    placement: Placement | None = None,
    log_filepath: str | None = None,
) -> dict[str, str | int]:
    """
    Process BASEMENT simulation results.

    Args:
        results_config_file   : Path to the configuration file for processing results.
        results_filepath      : Path to the simulation results file.
        results_output_file   : Path to the output file for processed results.
        run_options           : Optional dict with keys like
                                 ``verbose`` (bool) and ``basement_path`` (str).
        placement             : Optional CPU socket, cores and GPU card to run on.
        log_filepath          : Optional text file BASEMENT's output is appended to.

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
    """
    return run_basement_exe(
        exe_name=f"BMv4_results{utils.EXE_SUFFIX}",
        input_files=[results_config_file, results_filepath],
        output_filepath=results_output_file,
        run_options=run_options,
        placement=placement,
        log_filepath=log_filepath,
    )


def make_xdmf_relative(xdmf_filepath: str) -> bool:
    """
    Makes the h5 references of an xdmf file relative to its own folder.

    BMv4_results is given absolute paths, so the xdmf may point to its h5 files with the
    full folder path. Without it, the folder can be moved or copied and still opened in ParaView.
    References to files in other folders are left as they are.

    Args:
        xdmf_filepath: Path to the xdmf file written by BMv4_results.

    Returns:
        True if the file was changed.
    """
    try:
        with open(xdmf_filepath, encoding="utf-8") as file:
            text = file.read()
    except OSError as exc:
        logger.warning(f"Could not read {xdmf_filepath} to make its paths relative: {exc}")
        return False

    folder = os.path.dirname(os.path.abspath(xdmf_filepath))
    # The folder in both separator spellings, followed by a separator,
    # and not the tail of a longer path ("/data/home/..." is left alone for "/home/...")
    parts = [re.escape(part) for part in re.split(r"[\\/]+", folder) if part]
    prefix = r"(?<![\w.\\/-])[\\/]?" + r"[\\/]+".join(parts) + r"[\\/]+"
    flags = re.IGNORECASE if os.name == "nt" else 0
    relative = re.sub(prefix, "", text, flags=flags)

    if relative == text:
        return False
    try:
        with open(xdmf_filepath, "w", encoding="utf-8") as file:
            file.write(relative)
    except OSError as exc:
        logger.warning(f"Could not make the paths in {xdmf_filepath} relative: {exc}")
        return False
    return True


def model_update_filepaths(filepath_config: str, filepaths_support_files: dict) -> None:
    """
    Updates the file paths in the JSON configuration file.

    Parameters:
        filepath_config (str): Path to the JSON configuration file.
        filepaths_support_files (dict): Dictionary containing support files and their paths.

    Returns:
        None
    """

    def update_file_references(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    update_file_references(value)
                elif "file" in key.lower() and isinstance(value, str):
                    basename = os.path.basename(value)
                    if basename in filepaths_support_files:
                        obj[key] = filepaths_support_files[basename]
                    else:
                        msg = f"File '{basename}' not found in support files. Please check your configuration or support_files folder."
                        logging.error(msg)
                        raise FileNotFoundError(msg)
        elif isinstance(obj, list):
            for item in obj:
                update_file_references(item)

    # Load config
    with open(filepath_config) as file:
        config_data = json.load(file)

    # Update simulation name
    config_data["SETUP"]["simulation_name"] = os.path.splitext(os.path.basename(filepath_config))[0]

    # Update mesh file
    mesh_file = os.path.basename(mesh_name_from_json(filepath_config))
    config_data["SETUP"]["BASEHPC"]["BASEPLANE_2D"]["GEOMETRY"]["mesh_file"] = filepaths_support_files[mesh_file]

    # Recursively update file references
    hydraulics = config_data["SETUP"]["BASEHPC"]["BASEPLANE_2D"]["HYDRAULICS"]
    update_file_references(hydraulics.get("BOUNDARY", {}))
    update_file_references(hydraulics.get("INITIAL", {}))
    update_file_references(hydraulics.get("TURBULENCE", {}).get("INITIAL", {}))

    # Save updated config
    with open(filepath_config, "w") as file:
        json.dump(config_data, file, indent=4)


@dataclass(frozen=True)
class RtsStats:
    """Real-time speedup (simulated time / computing time) of a simulation."""

    final: float  # Over the whole run: BASEMENT's last progress value
    slowest: float  # Slowest speed between two progress lines
    fastest: float  # Fastest speed between two progress lines


def rts_stats(stdout: str) -> RtsStats | None:
    """
    Real-time speedup from the progress lines of BMv4_simulation --progress.

    BASEMENT prints "-> Progress: 37/100, dt = 0.29 [s], RTS = 3215.4", where RTS is a running
    average since the start. Line k/n has covered k/n of the simulated time, so its computing time
    is (k/n) / RTS in units of the simulated time span; the speed between two lines is the
    simulated time gained divided by the computing time spent (the time span cancels out).

    Args:
        stdout: Captured output of BMv4_simulation with --progress.

    Returns:
        The final RTS and the slowest and fastest speed between progress lines, or None
        without progress lines.
    """
    points = [
        (int(k) / int(n), float(rts))
        for k, n, rts in re.findall(r"Progress: (\d+)/(\d+),.*?RTS = ([-+\d.eE]+)", stdout)
        if int(n) > 0 and int(k) > 0 and float(rts) > 0
    ]
    if not points:
        return None

    speeds = []
    previous_fraction, previous_time = 0.0, 0.0
    for fraction, rts in points:
        time = fraction / rts  # computing time so far, in units of the simulated time span
        if fraction > previous_fraction and time > previous_time:
            speeds.append((fraction - previous_fraction) / (time - previous_time))
            previous_fraction, previous_time = fraction, time
    return RtsStats(points[-1][1], min(speeds, default=points[-1][1]), max(speeds, default=points[-1][1]))
