#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Import libraries
import concurrent.futures
import logging
import shutil
import time
from pathlib import Path

from tqdm import tqdm

import capiq.basement_tools as bt
from capiq import utils

# Create a logger for run_simulations
logger = logging.getLogger("run_simulations")


def results_file(sim_config: Path | str, folder_output: Path) -> Path:
    """
    Returns the path of the final results file of a simulation.

    Args:
        sim_config: Path or name of the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.

    Returns:
        Path to "<NAME>_results.h5" in the output folder.
    """
    basename = Path(sim_config).stem.replace("_model", "")
    return folder_output / f"{basename}_results.h5"


def simulation_completed(sim_config: Path | str, folder_output: Path) -> bool:
    """
    Checks whether a simulation already produced its final results file.

    Args:
        sim_config: Path to the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.

    Returns:
        True if the "*_results.h5" output already exists.
    """
    return results_file(sim_config, folder_output).exists()


def calculate(
    sim_config: Path | str,
    paths: dict,
    user_opts: dict,
    gpu: bool = False,
) -> float:
    """
    Run the simulation.

    Args:
        sim_config: Path to the simulation config file.
        paths: Dictionary containing the paths to the folders.
        user_opts: Dictionary containing the user options.
        gpu: Flag to indicate if the simulation should be run on GPU.
              This is only used if there are simultaneous runs.

    Returns:
        Elapsed time in seconds.
    """
    # Convert to Path if string
    sim_config = Path(sim_config)
    sim_config_str = str(sim_config)

    # Start time
    t_start = time.time()

    # Sets file paths
    basename = sim_config.stem.replace("_model", "")

    # json files
    folder_input = Path(paths["folder_input"])
    folder_output = Path(paths["folder_output"])

    run_config = folder_input / f"{basename}_simulation.json"
    results_config = paths["results_filepath"]

    # h5 files
    setup_path = folder_output / f"{basename}_setup.h5"
    results_path = folder_output / f"{basename}_results.h5"

    # xdmf files
    xdmf_path = folder_output / f"{basename}_results.xdmf"

    # Update support file paths
    local_paths = {}
    local_paths.update(paths["meshes"].copy())
    local_paths.update(paths["support_files"].copy())
    # Initialization files produced in this run are read from the output folder,
    # files from the initialization folder take priority
    local_paths.update(
        {name: str(results_file(producer, folder_output)) for name, producer in paths.get("produced", {}).items()}
    )
    local_paths.update(paths.get("initialization_files", {}).copy())
    bt.model_update_filepaths(sim_config_str, local_paths)

    # Run setup
    bt.run_setup(sim_config_str, str(setup_path), user_opts["simulation_options"])

    # Run the simulation
    if gpu:
        backend = user_opts["simulation_options"].get("gpu_backend", "cudaC")
        if backend not in ["cuda", "cudaC"]:
            logger.warning(f"Invalid GPU backend specified: {backend}. Falling back to cudaC.")
            backend = "cudaC"

        bt.run_simulation(
            str(run_config),
            str(setup_path),
            str(results_path),
            user_opts["simulation_options"],
            override_backend=backend,
        )
    else:
        bt.run_simulation(
            str(run_config),
            str(setup_path),
            str(results_path),
            user_opts["simulation_options"],
        )

    # Run the results
    bt.run_results(
        str(results_config),
        str(results_path),
        str(xdmf_path),
        user_opts["simulation_options"],
    )

    # Copies json files to the output folder
    if user_opts.get("store_configs", False):
        shutil.copy2(sim_config, folder_output / f"{basename}_model.json")
        shutil.copy2(run_config, folder_output / f"{basename}_simulation.json")

    # End time
    t_end = time.time()

    return t_end - t_start


def ready_simulations(
    pending: list[str],
    dependencies: dict[str, set[str]],
    succeeded: set[str],
    failed: set[str],
) -> tuple[list[str], list[str]]:
    """
    Splits the pending simulations into the ones that can run now and the ones that never will.

    Args:
        pending: Model file names still to run, in running order.
        dependencies: {model file name: set of model file names to run first}.
        succeeded: Model file names that finished successfully.
        failed: Model file names that failed or were skipped.

    Returns:
        ready: simulations whose dependencies all succeeded, in running order.
        blocked: simulations with a failed or skipped dependency.
    """
    ready, blocked = [], []
    for sim in pending:
        deps = dependencies.get(sim, set())
        if deps & failed:
            blocked.append(sim)
        elif deps <= succeeded:
            ready.append(sim)
    return ready, blocked


def store_initialization(sim: str, produced: dict[str, str], paths: dict) -> None:
    """
    Copies the results of a simulation used as initialization to the initialization folder,
    so that later runs find it there.

    Args:
        sim: Model file name of the finished simulation.
        produced: {required file name: model file name that produces it}.
        paths: Dictionary containing the paths to the folders.
    """
    folder_initialization = paths.get("folder_initialization")
    if folder_initialization is None:
        return

    for results_name, producer in produced.items():
        if producer != sim:
            continue
        # Stored under the name the model files ask for, so later runs find it directly
        source = results_file(producer, Path(paths["folder_output"]))
        target = Path(folder_initialization) / results_name
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            logger.info(f"Initialization file {results_name} copied to {folder_initialization}")
        except OSError as exc:
            logger.warning(f"Could not copy initialization file {results_name} to {folder_initialization}: {exc}")


@utils.timeit(logger, message_end="All simulations calculated in {elapsed:.2f} seconds")
def calculate_queue(dict_files: dict, paths: dict, user_opts: dict) -> None:
    """
    Main function to run the simulations.

    Args:
        dict_files: Dictionary containing the required filepaths
        paths: Dictionary containing the paths to the folders.
        user_opts: Dictionary containing the user options.
    """
    logger.info("Running simulations")

    # Extract simulations dictionary (already in running order: initializations first)
    dict_simulations = dict_files["simulations_to_run"].copy()
    dependencies = dict_files.get("dependencies", {})
    produced = dict_files.get("produced", {})

    # Inject the meshes, support and initialization files into the paths dictionary
    local_paths = paths.copy()
    local_paths["meshes"] = dict_files["meshes"].copy()
    local_paths["support_files"] = dict_files["support_files"].copy()
    local_paths["initialization_files"] = dict_files.get("initialization_files", {}).copy()
    local_paths["produced"] = produced.copy()

    # Extract user options
    parallel_mode = user_opts["simulation_options"].get("parallel", False)
    overwrite = user_opts["simulation_options"].get("overwrite", False)

    succeeded: set[str] = set()
    failed: set[str] = set()
    skipped: list[str] = []

    # Skip simulations that already have final results, unless overwrite is requested
    if not overwrite:
        folder_output = Path(paths["folder_output"])
        already_done = [
            name for name, filepath in dict_simulations.items() if simulation_completed(filepath, folder_output)
        ]
        for name in already_done:
            del dict_simulations[name]
            succeeded.add(name)
            store_initialization(name, produced, local_paths)

        if already_done:
            logger.info(f"Resuming: skipping {len(already_done)} already completed simulation(s): {already_done}")

    # Total number of simulations
    total_sims = len(dict_simulations)
    pending = list(dict_simulations)

    def skip_blocked(pbar) -> None:
        """Removes the pending simulations whose initialization failed."""
        _, blocked = ready_simulations(pending, dependencies, succeeded, failed)
        for sim in blocked:
            logger.error(f"Simulation {sim} skipped: its initialization simulation failed or was skipped")
            pending.remove(sim)
            failed.add(sim)
            skipped.append(sim)
            pbar.update(1)

    def finish(sim: str, elapsed_time: float | None, exc: BaseException | None) -> None:
        """Records the outcome of a simulation."""
        sim_name = Path(dict_simulations[sim]).stem.replace("_model", "")
        if exc is None:
            logger.info(f"Simulation {sim_name} finished. Elapsed time: {elapsed_time:.2f} seconds")
            succeeded.add(sim)
            store_initialization(sim, produced, local_paths)
        else:
            logger.error(f"Simulation {sim_name} generated an exception: {exc}")
            failed.add(sim)

    pbar = tqdm(
        total=total_sims,
        desc="Simulations",
        unit="sim",
        ncols=80,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
    )

    if parallel_mode:
        logger.info(f"Running {total_sims} simulations simultaneously")

        # Configurable: split between GPU and CPU workers
        n_gpu = user_opts["simulation_options"].get("n_gpus", 0)
        n_cpu = user_opts["simulation_options"].get("n_sim_cpus", 1)

        logger.info(f"Using {n_gpu} GPU(s) and {n_cpu} CPU(s) for simulations")
        logger.info(f"Total number of workers: {n_gpu + n_cpu}")

        # Overrides backend and nthreads
        local_user_opts = user_opts.copy()

        # Executors
        if n_gpu > 0:
            gpu_executor = concurrent.futures.ProcessPoolExecutor(max_workers=n_gpu)
        cpu_executor = concurrent.futures.ProcessPoolExecutor(max_workers=n_cpu)

        cpu_futures: set = set()
        gpu_futures: set = set()
        future_to_sim: dict = {}

        # Main execution loop
        while pending or gpu_futures or cpu_futures:
            # First check for finished tasks
            done, _ = concurrent.futures.wait(
                gpu_futures | cpu_futures,
                timeout=0.1,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                sim = future_to_sim.pop(future)
                try:
                    finish(sim, future.result(), None)
                except Exception as exc:
                    finish(sim, None, exc)

                # Update progress bar
                pbar.update(1)

                if future in gpu_futures:
                    gpu_futures.remove(future)
                else:
                    cpu_futures.remove(future)

            # Drop simulations that can no longer run
            skip_blocked(pbar)

            # Assign ready work (initializations first) to any available slots
            ready, _ = ready_simulations(pending, dependencies, succeeded, failed)
            for sim in ready:
                if n_gpu > 0 and len(gpu_futures) < n_gpu:
                    future = gpu_executor.submit(calculate, dict_simulations[sim], local_paths, local_user_opts, True)
                    gpu_futures.add(future)
                elif len(cpu_futures) < n_cpu:
                    future = cpu_executor.submit(calculate, dict_simulations[sim], local_paths, local_user_opts)
                    cpu_futures.add(future)
                else:
                    break

                pending.remove(sim)
                future_to_sim[future] = sim

        if n_gpu > 0:
            gpu_executor.shutdown()
        cpu_executor.shutdown()

    else:
        # Run simulations sequentially, in running order
        logger.info(f"Running {total_sims} simulations sequentially")

        while pending:
            skip_blocked(pbar)
            if not pending:
                break

            sim = pending.pop(0)
            try:
                finish(sim, calculate(dict_simulations[sim], local_paths, user_opts), None)
            except Exception as exc:
                finish(sim, None, exc)

            # Update progress bar
            pbar.update(1)

    pbar.close()

    run_failed = sorted(failed - set(skipped))
    if run_failed:
        logger.error(f"{len(run_failed)} simulation(s) failed: {run_failed}")
    if skipped:
        logger.error(f"{len(skipped)} simulation(s) skipped because their initialization failed: {skipped}")
