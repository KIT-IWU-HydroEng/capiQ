#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

"""
Runs the simulation queue in parallel on CPU sockets and GPUs, resuming or skipping earlier runs.
"""

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Import libraries
import concurrent.futures
import contextlib
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from tqdm import tqdm

import capiq.basement_tools as bt
from capiq import cpu_topology, resume, utils
from capiq.cpu_topology import Placement
from capiq.resume import ResumePlan

# Create a logger for run_simulations
logger = logging.getLogger("run_simulations")


def simulation_folder(sim_config: Path | str, folder_output: Path, subfolders: bool = True) -> Path:
    """
    Returns the folder holding the output files of a simulation.

    Args:
        sim_config: Path or name of the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.
        subfolders: True puts each simulation in its own folder "output/<NAME>/",
                    False puts all files directly in the output folder.

    Returns:
        "output/<NAME>" or "output".
    """
    if not subfolders:
        return Path(folder_output)
    basename = Path(sim_config).stem.replace("_model", "")
    return Path(folder_output) / basename


def results_file(sim_config: Path | str, folder_output: Path, subfolders: bool = True) -> Path:
    """
    Returns the path of the final results file of a simulation.

    Args:
        sim_config: Path or name of the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.
        subfolders: Whether each simulation has its own folder in the output folder.

    Returns:
        Path to "<NAME>_results.h5" in the simulation's output folder.
    """
    basename = Path(sim_config).stem.replace("_model", "")
    return simulation_folder(sim_config, folder_output, subfolders) / f"{basename}_results.h5"


def resume_plan(sim_config: Path | str, folder_output: Path, subfolders: bool = True) -> ResumePlan:
    """
    Decides what to do with a simulation from what it left in the output folder:
    skip it (complete), continue it from its last good output, or run it from the start.

    The outputs are counted against SIMULATION.TIME of the input "<NAME>_simulation.json" next to the
    model file, so an end time changed after the run started is taken into account.

    Args:
        sim_config: Path to the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.
        subfolders: Whether each simulation has its own folder in the output folder.
    """
    results = results_file(sim_config, folder_output, subfolders)
    basename = results.name.removesuffix("_results.h5")
    run_config = Path(sim_config).with_name(f"{basename}_simulation.json")
    return resume.plan_resume(
        results, results.with_suffix(".xdmf"), results.with_name(f"{basename}_setup.h5"), run_config
    )


def simulation_completed(sim_config: Path | str, folder_output: Path, subfolders: bool = True) -> bool:
    """
    Checks whether a simulation finished: its results file holds every output the simulation asked for,
    and the .xdmf (written after the simulation succeeded) is there.

    Args:
        sim_config: Path to the "*_model.json" file for the simulation.
        folder_output: Path to the output folder.
        subfolders: Whether each simulation has its own folder in the output folder.
    """
    return resume_plan(sim_config, folder_output, subfolders).action == "complete"


def calculate(
    sim_config: Path | str,
    paths: dict,
    user_opts: dict,
    gpu: bool = False,
    placement: Placement | None = None,
    plan: ResumePlan | None = None,
) -> tuple[float, bt.RtsStats | None]:
    """
    Run the simulation, or continue it from its last good output.

    Args:
        sim_config: Path to the simulation config file.
        paths: Dictionary containing the paths to the folders.
        user_opts: Dictionary containing the user options.
        gpu: Flag to indicate if the simulation should be run on GPU.
              This is only used if there are simultaneous runs.
        placement: CPU socket, cores and GPU card to run on; None runs unpinned.
        plan: What to do with the files a previous run left (``resume_plan``); None runs from the start.

    Returns:
        Elapsed time in seconds, and BASEMENT's real-time speedup (None without progress lines).
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
    subfolders = paths.get("output_subfolders", True)
    # All files of this simulation go here: "output/<NAME>/" or "output/"
    folder_sim = simulation_folder(sim_config, folder_output, subfolders)
    folder_sim.mkdir(parents=True, exist_ok=True)

    run_config = folder_input / f"{basename}_simulation.json"
    results_config = paths["results_filepath"]

    # h5 files
    setup_path = folder_sim / f"{basename}_setup.h5"
    results_path = folder_sim / f"{basename}_results.h5"

    # xdmf files
    xdmf_path = folder_sim / f"{basename}_results.xdmf"

    # BASEMENT's own output, written while it runs and started fresh for every run:
    # the setup in one file, the simulation and the results in the other
    setup_log = folder_sim / f"{basename}_setup.log"
    run_log = folder_sim / f"{basename}_run.log"

    action = plan.action if plan is not None else "new"
    if action in ("new", "scratch"):
        # Files a previous run left are moved aside, not deleted (also when it ran from the start)
        for path in (results_path, resume.backup_file(results_path)):
            if path.exists():
                os.replace(path, resume.unusable_file(path))
        for log in (setup_log, run_log, folder_sim / f"{basename}_basement.log"):  # _basement.log: older capiQ versions
            log.unlink(missing_ok=True)
    # A continuation appends to the logs of the run it continues

    # Update support file paths
    local_paths = {}
    local_paths.update(paths["meshes"].copy())
    local_paths.update(paths["support_files"].copy())
    # Initialization files produced in this run are read from the output folder,
    # files from the initialization folder take priority
    local_paths.update(
        {
            name: str(results_file(producer, folder_output, subfolders))
            for name, producer in paths.get("produced", {}).items()
        }
    )
    local_paths.update(paths.get("initialization_files", {}).copy())
    # The model file BASEMENT's setup reads, with the full paths of its files, is written next to the
    # results: the input file is never changed. It stays there with store_configs (default: on).
    setup_model = folder_sim / f"{basename}_model.json"
    bt.model_update_filepaths(sim_config_str, local_paths, str(setup_model))

    # Run setup (a continuation reuses the setup file of the run it continues)
    try:
        if action in ("new", "scratch"):
            bt.run_setup(
                str(setup_model),
                str(setup_path),
                user_opts["simulation_options"],
                placement=placement,
                log_filepath=str(setup_log),
            )
    finally:
        if not user_opts.get("store_configs", True):
            setup_model.unlink(missing_ok=True)

    # Run the simulation
    backend = None
    if gpu:
        backend = user_opts["simulation_options"].get("gpu_backend", "cudaC")
        if backend not in ["cuda", "cudaC"]:
            logger.warning(f"Invalid GPU backend specified: {backend}. Falling back to cudaC.")
            backend = "cudaC"

    rts = None
    if action in ("new", "scratch", "continue"):
        simulation_config = run_config
        if action == "continue" and plan is not None:
            # BASEMENT's re-run: same setup file, results appended to the partial file,
            # SIMULATION.TIME.start = time of its last good output
            resume.prepare_continuation(results_path, plan.last_index)
            simulation_config = folder_sim / f"{basename}_continue_simulation.json"
            resume.set_continuation_start(run_config, simulation_config, plan.restart_time)

        output = bt.run_simulation(
            str(simulation_config),
            str(setup_path),
            str(results_path),
            user_opts["simulation_options"],
            override_backend=backend,
            placement=placement,
            log_filepath=str(run_log),
        )
        rts = bt.rts_stats(str(output["stdout"]))
        if simulation_config != run_config:
            simulation_config.unlink(missing_ok=True)

    # Puts back the output BASEMENT rewrote at the restart time, removes the backup, and stores the
    # original start with the planned end (the input's end may have changed since the run started)
    planned = resume.read_simulation_time(run_config)
    end_out = (planned[1], planned[2]) if planned is not None else None
    if end_out is not None:
        resume.finish_continuation(results_path, *end_out)
    else:
        resume.finish_continuation(results_path)
    status = resume.inspect_results(results_path, end_out)
    if not status.complete:
        raise RuntimeError(
            f"{results_path.name} is incomplete after the simulation: "
            f"{status.good} of {status.expected} outputs {status.error}".rstrip()
        )

    # Run the results
    bt.run_results(
        str(results_config),
        str(results_path),
        str(xdmf_path),
        user_opts["simulation_options"],
        placement=placement,
        log_filepath=str(run_log),
    )
    # The xdmf finds its h5 files next to it, so the folder can be moved and opened in ParaView
    bt.make_xdmf_relative(str(xdmf_path))

    # Copies the simulation file to the simulation's output folder, next to the model file BASEMENT read
    # (default: on, so the results keep their inputs)
    if user_opts.get("store_configs", True):
        shutil.copy2(run_config, folder_sim / f"{basename}_simulation.json")

    # End time
    t_end = time.time()

    return t_end - t_start, rts


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


def choose_device(preferred: str, gpu_free: bool, cpu_free: bool) -> str | None:
    """
    Chooses the worker for the next simulation.

    Args:
        preferred: "gpu" or "cpu", used when both a GPU and a CPU worker are free.
        gpu_free: Whether a GPU worker is free.
        cpu_free: Whether a CPU worker is free.

    Returns:
        "gpu", "cpu", or None if no worker is free.
    """
    if gpu_free and cpu_free:
        return preferred
    if gpu_free:
        return "gpu"
    if cpu_free:
        return "cpu"
    return None


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
        source = results_file(producer, Path(paths["folder_output"]), paths.get("output_subfolders", True))
        target = Path(folder_initialization) / results_name
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            logger.info(f"Initialization file {results_name} copied to {folder_initialization}")
        except OSError as exc:
            logger.warning(f"Could not copy initialization file {results_name} to {folder_initialization}: {exc}")


@dataclass(frozen=True)
class QueueOutcome:
    """Model files of the simulations that did not run successfully in this call of calculate_queue."""

    failed: list[str] = field(default_factory=list)  # BASEMENT or capiQ failed
    blocked: list[str] = field(default_factory=list)  # not run: their initialization simulation failed
    already_complete: list[str] = field(default_factory=list)  # not run: complete from an earlier run

    @property
    def exit_code(self) -> int:
        """2: a simulation failed (or was blocked by a failure), 1: complete ones were skipped, 0: all ran."""
        if self.failed or self.blocked:
            return 2
        if self.already_complete:
            return 1
        return 0


@utils.timeit(logger, message_end="All simulations calculated in {elapsed:.2f} seconds")
def calculate_queue(dict_files: dict, paths: dict, user_opts: dict) -> QueueOutcome:
    """
    Main function to run the simulations.

    Args:
        dict_files: Dictionary containing the required filepaths
        paths: Dictionary containing the paths to the folders.
        user_opts: Dictionary containing the user options.

    Returns:
        The simulations that failed, that were skipped because their initialization failed, and that
        were skipped because an earlier run completed them (all empty when every simulation ran and
        succeeded). Its exit_code is the exit code of capiQ.
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
    # One folder per simulation in the output folder (default), or all files directly in it
    subfolders = bool(user_opts.get("output_subfolders", True))
    local_paths["output_subfolders"] = subfolders

    # Extract user options
    sim_opts = user_opts["simulation_options"]
    parallel_mode = sim_opts.get("parallel", False)
    overwrite = sim_opts.get("overwrite", False)
    n_threads = int(sim_opts.get("n_sim_threads", os.cpu_count() or 1))

    succeeded: set[str] = set()
    failed: set[str] = set()
    skipped: list[str] = []

    # What each simulation left in the output folder: skip the complete ones, continue the partial ones
    # (overwrite: the output folder was emptied, every simulation runs from the start)
    plans: dict[str, ResumePlan] = {}
    already_done: list[str] = []
    if not overwrite:
        folder_output = Path(paths["folder_output"])
        plans = {name: resume_plan(filepath, folder_output, subfolders) for name, filepath in dict_simulations.items()}
        already_done = [name for name, plan in plans.items() if plan.action == "complete"]
        for name, plan in plans.items():
            if plan.action != "new":
                sim_name = Path(dict_simulations[name]).stem.replace("_model", "")
                log = logger.warning if plan.action == "scratch" else logger.info
                log(f"Simulation {sim_name}: {plan.describe()}")
        # Only complete runs are skipped and stored as initialization: never a partial file
        for name in already_done:
            del dict_simulations[name]
            succeeded.add(name)
            store_initialization(name, produced, local_paths)

        if already_done:
            logger.info(f"Resuming: skipping {len(already_done)} already completed simulation(s): {already_done}")

    # Total number of simulations
    total_sims = len(dict_simulations)
    pending = list(dict_simulations)
    if not pending:
        # Nothing left: no hardware detection, no worker processes
        logger.info("Nothing to run: all simulations are already completed (set overwrite: true to run them again)")
        return QueueOutcome(already_complete=already_done)

    def skip_blocked(pbar) -> None:
        """Removes the pending simulations whose initialization failed."""
        _, blocked = ready_simulations(pending, dependencies, succeeded, failed)
        for sim in blocked:
            logger.error(f"Simulation {sim} skipped: its initialization simulation failed or was skipped")
            pending.remove(sim)
            failed.add(sim)
            skipped.append(sim)
            pbar.update(1)

    def finish(sim: str, outcome: tuple[float, bt.RtsStats | None] | None, exc: BaseException | None) -> None:
        """Records the outcome of a simulation: (elapsed seconds, real-time speedup) from calculate."""
        sim_name = Path(dict_simulations[sim]).stem.replace("_model", "")
        if exc is None and outcome is not None:
            elapsed_time, rts = outcome
            duration = utils.format_duration(elapsed_time)
            logger.info(f"Simulation {sim_name} finished. Elapsed time: {elapsed_time:.2f} seconds ({duration})")
            if rts is not None:
                logger.info(
                    f"Simulation {sim_name} real-time speedup: RTS = {rts.final:.1f} "
                    f"(range {rts.slowest:.1f}-{rts.fastest:.1f})"
                )
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

        # Device used when both a GPU and a CPU worker are free
        preferred_device = str(user_opts["simulation_options"].get("preferred_device", "gpu")).lower()
        if preferred_device not in ("gpu", "cpu"):
            logger.warning(f"Invalid preferred device specified: {preferred_device}. Falling back to gpu.")
            preferred_device = "gpu"
        if n_gpu > 0 and n_cpu > 0:
            logger.info(f"Preferred device when both are free: {preferred_device}")

        # Overrides backend and nthreads
        local_user_opts = user_opts.copy()

        # CPU sockets and GPU cards each run is placed on
        resources = cpu_topology.setup_resources(sim_opts, n_threads, n_gpu)
        cpu_cores, host_cores, gpu_slots = resources.cpu_cores, resources.host_cores, resources.gpus

        # The workers' log records go to this process's log (closed in the finally below, after the pools)
        worker_log = contextlib.ExitStack()
        initializer, initargs = worker_log.enter_context(utils.worker_logging())

        # Executors
        if n_gpu > 0:
            gpu_executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=n_gpu, initializer=initializer, initargs=initargs
            )
        cpu_executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=n_cpu, initializer=initializer, initargs=initargs
        )

        cpu_futures: set = set()
        gpu_futures: set = set()
        future_to_sim: dict = {}
        # Cores and GPU worker held by each running simulation, released when it ends
        future_to_resources: dict = {}

        try:
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

                    gpu_slot, placement = future_to_resources.pop(future)
                    if host_cores is not None:
                        host_cores.release(placement)
                    if gpu_slots is not None and gpu_slot is not None:
                        gpu_slots.release(gpu_slot)

                # Drop simulations that can no longer run
                skip_blocked(pbar)

                # Assign ready work (initializations first) to any available slots
                ready, _ = ready_simulations(pending, dependencies, succeeded, failed)
                for sim in ready:
                    # A pinned CPU run also needs enough free cores inside one socket
                    cpu_free = len(cpu_futures) < n_cpu
                    placement = None
                    if cpu_free and cpu_cores is not None:
                        placement = cpu_cores.acquire(n_threads)
                        cpu_free = placement is not None

                    device = choose_device(
                        preferred_device,
                        gpu_free=gpu_slots is not None and gpu_slots.free(),
                        cpu_free=cpu_free,
                    )
                    if device != "cpu" and cpu_cores is not None:
                        # Cores reserved above are not used
                        cpu_cores.release(placement)

                    gpu_slot = None
                    if device == "gpu":
                        gpu_slot, placement = gpu_slots.acquire(host_cores)  # type: ignore[union-attr]
                        future = gpu_executor.submit(
                            calculate,
                            dict_simulations[sim],
                            local_paths,
                            local_user_opts,
                            True,
                            placement,
                            plans.get(sim),
                        )
                        gpu_futures.add(future)
                    elif device == "cpu":
                        future = cpu_executor.submit(
                            calculate,
                            dict_simulations[sim],
                            local_paths,
                            local_user_opts,
                            False,
                            placement,
                            plans.get(sim),
                        )
                        cpu_futures.add(future)
                    else:
                        break

                    # GPU runs always have a placement, CPU runs only when pinned
                    sim_name = Path(dict_simulations[sim]).stem.replace("_model", "")
                    where = placement.describe() if placement is not None else f"CPU, {n_threads} threads, not pinned"
                    logger.info(f"Simulation {sim_name} started on {where}")

                    pending.remove(sim)
                    future_to_sim[future] = sim
                    future_to_resources[future] = (gpu_slot, placement)

            if n_gpu > 0:
                gpu_executor.shutdown()
            cpu_executor.shutdown()
        except KeyboardInterrupt:
            logger.warning("Interrupted: stopping the running simulations")
            pbar.close()
            executors = [cpu_executor, gpu_executor] if n_gpu > 0 else [cpu_executor]
            # All worker processes at once, with the BASEMENT runs they started
            # (killing one worker makes the pool stop the others, which would orphan their runs)
            workers = [pid for executor in executors for pid in list(getattr(executor, "_processes", None) or {})]
            utils.kill_process_trees(workers)
            for executor in executors:
                executor.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            # After the pools: the workers' last records are written to the log first
            worker_log.close()

    else:
        # Run simulations sequentially, in running order
        logger.info(f"Running {total_sims} simulations sequentially")

        # Every run on the same cores of one socket
        cpu_cores = cpu_topology.setup_resources(sim_opts, n_threads, 0).cpu_cores
        placement = cpu_cores.acquire(n_threads) if cpu_cores is not None else None
        if placement is not None:
            logger.info(f"Simulations run on {placement.describe()}")

        while pending:
            skip_blocked(pbar)
            if not pending:
                break

            sim = pending.pop(0)
            try:
                outcome = calculate(dict_simulations[sim], local_paths, user_opts, False, placement, plans.get(sim))
                finish(sim, outcome, None)
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
    return QueueOutcome(failed=run_failed, blocked=skipped, already_complete=already_done)
