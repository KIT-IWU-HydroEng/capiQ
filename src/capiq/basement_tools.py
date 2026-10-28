#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Import libraries
import json
import logging
import os
import subprocess

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


def run_basement_exe(
    exe_name: str,
    input_files: list[str] | None = None,
    output_filepath: str | None = None,
    run_options: dict | None = None,
    extra_args: list[str] | None = None,
) -> dict[str, str | int]:
    """
    Execute a BASEMENT executable and capture its output.

    Args:
        exe_name          : Name of the BASEMENT executable
                            (e.g. ``"BMv4_setup.exe"``, ``"BMv4_simulation.exe"``).
        input_files       : List of input file paths (e.g. config files).
        output_filepath   : Path for the output file.
        run_options       : Optional dict with keys like
                             ``verbose`` (bool) and ``basement_path`` (str).
        extra_args        : Additional command-line arguments
                            (e.g. ``["--backend", "omp", "--nthreads", "4"]``).

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
    """
    if run_options is None:
        run_options = {}

    # Resolve BASEMENT installation path
    basement_path = c.BASEMENT_PATH or run_options.get(
        "basement_path",
        r"C:\Program Files\BASEMENT 4.3.0\bin",
    )
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

    # Run the subprocess and capture both streams
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        logging.error(f"Unable to start {exe_path!r}: {exc}")
        raise

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
        logging.error(f"'{exe_name}' failed (return code {completed.returncode}). Command: {' '.join(cmd)}")
        if completed.stderr:
            logging.error("--- STDERR ---")
            logging.error(completed.stderr)
        if completed.stdout:
            logging.info("--- STDOUT (extra info) ---")
            logging.info(completed.stdout)

        raise Exception(f"{exe_name} failed. Check the log for details.")

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
) -> dict[str, str | int]:
    """
    Execute the BASEMENT setup process.

    Args:
        config_filepath : Path to the simulation configuration file.
        setup_filepath  : Path where the generated setup file will be written.
        run_options     : Optional dict with keys like
                           ``verbose`` (bool) and ``basement_path`` (str).

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
    """
    return run_basement_exe(
        exe_name="BMv4_setup.exe",
        input_files=[config_filepath],
        output_filepath=setup_filepath,
        run_options=run_options,
    )


def run_simulation(
    run_config_filepath: str,
    setup_filepath: str,
    results_filepath: str,
    run_options: dict | None = None,
    override_backend: str | None = None,
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
        exe_name="BMv4_simulation.exe",
        input_files=[run_config_filepath, setup_filepath],
        output_filepath=results_filepath,
        run_options=run_options,
        extra_args=["--backend", backend, "--nthreads", str(nthreads)],
    )


def run_results(
    results_config_file: str,
    results_filepath: str,
    results_output_file: str,
    run_options: dict | None = None,
) -> dict[str, str | int]:
    """
    Process BASEMENT simulation results.

    Args:
        results_config_file   : Path to the configuration file for processing results.
        results_filepath      : Path to the simulation results file.
        results_output_file   : Path to the output file for processed results.
        run_options           : Optional dict with keys like
                                 ``verbose`` (bool) and ``basement_path`` (str).

    Returns:
        dict with keys ``stdout`` (str), ``stderr`` (str) and ``returncode`` (int).
    """
    return run_basement_exe(
        exe_name="BMv4_results.exe",
        input_files=[results_config_file, results_filepath],
        output_filepath=results_output_file,
        run_options=run_options,
    )


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
