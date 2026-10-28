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
import queue
import shutil
import time
from pathlib import Path

from tqdm import tqdm

import capiq.basement_tools as bt
from capiq import utils

# Create a logger for run_simulations
logger = logging.getLogger("run_simulations")


def simulation_completed(sim_config: Path | str, folder_output: Path) -> bool:
    """
    Checks whether a simulation already produced its final results file.

    Args:
        sim_config: Path to the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.

    Returns:
        True if the "*_results.h5" output already exists.
    """
    basename = Path(sim_config).stem.replace("_model", "")
    h5_path = folder_output / f"{basename}_results.h5"
    return h5_path.exists()


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

    # Extract simulations dictionary
    dict_simulations = dict_files["simulations_to_run"].copy()

    # Inject the meshes and support files into the paths dictionary
    local_paths = paths.copy()
    local_paths["meshes"] = dict_files["meshes"].copy()
    local_paths["support_files"] = dict_files["support_files"].copy()

    # Extract user options
    parallel_mode = user_opts["simulation_options"].get("parallel", False)
    overwrite = user_opts["simulation_options"].get("overwrite", False)

    # Skip simulations that already have final results, unless overwrite is requested
    if not overwrite:
        folder_output = Path(paths["folder_output"])
        already_done = [
            name for name, filepath in dict_simulations.items() if simulation_completed(filepath, folder_output)
        ]
        for name in already_done:
            del dict_simulations[name]

        if already_done:
            logger.info(f"Resuming: skipping {len(already_done)} already completed simulation(s): {already_done}")

    # Total number of simulations
    total_sims = len(dict_simulations)

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

        # Task management
        pending_sims: queue.Queue[str] = queue.Queue()
        for sim in dict_simulations.values():
            pending_sims.put(sim)

        cpu_futures: set = set()
        gpu_futures: set = set()
        future_to_sim: dict = {}

        # Create progress bar
        pbar = tqdm(
            total=total_sims,
            desc="Simulations",
            unit="sim",
            ncols=80,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        )

        # Main execution loop
        while not pending_sims.empty() or gpu_futures or cpu_futures:
            # First check for finished tasks
            done, _ = concurrent.futures.wait(
                gpu_futures | cpu_futures,
                timeout=0.1,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                sim = future_to_sim.pop(future)
                sim_name = Path(sim).stem.replace("_model", "")
                try:
                    elapsed_time = future.result()
                    logger.info(f"Simulation {sim_name} finished. Elapsed time: {elapsed_time:.2f} seconds")
                except Exception as exc:
                    logger.error(f"Simulation {sim_name} generated an exception: {exc}")

                # Update progress bar
                pbar.update(1)

                if future in gpu_futures:
                    gpu_futures.remove(future)
                else:
                    cpu_futures.remove(future)

            # Assign new work to any available slots
            while not pending_sims.empty() and ((n_gpu > 0 and len(gpu_futures) < n_gpu) or len(cpu_futures) < n_cpu):
                sim = pending_sims.get()

                if n_gpu > 0 and len(gpu_futures) < n_gpu:
                    future = gpu_executor.submit(
                        calculate,
                        sim,
                        local_paths,
                        local_user_opts,
                        True,
                    )
                    gpu_futures.add(future)
                else:
                    future = cpu_executor.submit(
                        calculate,
                        sim,
                        local_paths,
                        local_user_opts,
                    )
                    cpu_futures.add(future)

                future_to_sim[future] = sim

        pbar.close()

    else:
        # Run simulations sequentially
        logger.info(f"Running {total_sims} simulations sequentially")

        # Create progress bar
        with tqdm(
            total=total_sims,
            desc="Simulations",
            unit="sim",
            ncols=80,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            for simulation in dict_simulations.values():
                sim_name = Path(simulation).stem.replace("_model", "")

                # Run the simulation
                elapsed_time = calculate(simulation, local_paths, user_opts)

                logger.info(f"Simulation {sim_name} finished. Elapsed time: {elapsed_time:.2f} seconds")

                # Update progress bar
                pbar.update(1)
