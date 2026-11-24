#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Libraries
import logging
import os

import capiq.basement_tools as bt
from capiq import utils

# Create a logger for file_import.py
logger = logging.getLogger("file_import")


def read_scenarios(folder_input: str) -> tuple[dict[str, str], str]:
    """
    This function sorts the scenarios to run.

    Args:
        folder_input (str): path to the folder containing the scenarios

    Returns:
        tuple: dictionary containing the scenarios to run, and the path to the results.json file
    """
    # Get the list of files in the input folder
    files = os.listdir(folder_input)
    sim_to_run = {}
    res_filepath = None

    # Removes the entries '_simulation*'
    for file in files:
        if "_model.json" in file:
            filepath = os.path.join(folder_input, file)
            sim_to_run[file] = filepath
        if "results.json" in file:
            res_filepath = os.path.join(folder_input, file)

    # Reports the number of scenarios to be run
    if len(sim_to_run) == 0:
        logger.error("No scenarios found in the input folder")
        raise Exception("No scenarios found in the input folder")

    if res_filepath is None:
        logger.error("No results.json file found in the input folder")
        raise Exception("No results.json file found in the input folder")

    if len(sim_to_run) == 1:
        logger.info(f"{len(sim_to_run)} scenario found")

    else:
        logger.info(f"{len(sim_to_run)} scenarios found")

    # Returns the scenarios to be run
    return sim_to_run, res_filepath


def read_meshes(folder_meshes: str) -> dict:
    """
    This function reads the meshes to be used in the simulations.

    Args:
        folder_meshes (str): path to the folder containing the meshes

    Returns:
        dict: dictionary containing the meshes to be used in the simulations
    """
    # Get the list of files in the meshes folder
    files = os.listdir(folder_meshes)
    meshes = {}

    # Adds the filepath to the meshes dictionary
    for file in files:
        if file.endswith(".2dm"):
            filepath = os.path.join(folder_meshes, file)
            meshes[file] = filepath

    if len(meshes) == 0:
        logger.error("No meshes found in the meshes folder")
        raise Exception("No meshes found in the meshes folder")

    if len(meshes) == 1:
        logger.info(f"{len(meshes)} mesh found")

    else:
        logger.info(f"{len(meshes)} meshes found")

    return meshes


def check_meshes(dict_simulation: dict, dict_mesh: dict) -> None:
    """
    This function checks if the meshes are available for the simulations.

    Args:
        simulation (dict): dictionary containing the simulation data
        mesh (dict): dictionary containing the mesh data

    Returns:
        None
    """
    for sim, path in dict_simulation.items():
        mesh_name = bt.mesh_name_from_json(path)
        mesh_name = os.path.basename(mesh_name)

        # Check if the mesh is available for the simulation
        if mesh_name not in dict_mesh.keys():
            logger.error(f"Mesh {mesh_name} not found in meshes folder")
            logger.error(f"Simulation {sim} requires mesh {mesh_name}")
            raise Exception(f"Mesh {mesh_name} not found in meshes folder. Simulation {sim} requires mesh {mesh_name}")


def read_support_files(folder_support: str) -> dict[str, str]:
    """
    This function reads the support files to be used in the simulations.
    The support files are optional and are not required for the simulations to run.

    Args:
        folder_support (str): path to the folder containing the support files

    Returns:
        dict: dictionary containing the support files to be used in the simulations (empty if there are none)
    """
    # Get the list of files in the support folder
    files = os.listdir(folder_support)
    support_files = {}

    # Adds the filepath to the support files dictionary
    for file in files:
        if file.endswith(".png"):
            continue
        fullpath = os.path.join(folder_support, file)
        support_files[file] = fullpath

    if len(support_files) == 0:
        logger.info("No support files found in the support folder")

    return support_files


def read_initialization_files(folder_initialization: str) -> dict[str, str]:
    """
    This function reads the initialization files available in the initialization folder.

    Args:
        folder_initialization (str): path to the folder containing the initialization files

    Returns:
        dict: dictionary {file name: file path} (empty if there are none)
    """
    initialization_files: dict[str, str] = {}
    if not os.path.isdir(folder_initialization):
        logger.info("No initialization folder found")
        return initialization_files

    for file in os.listdir(folder_initialization):
        filepath = os.path.join(folder_initialization, file)
        if os.path.isfile(filepath):
            initialization_files[file] = filepath

    logger.info(f"{len(initialization_files)} initialization file(s) found in the initialization folder")

    return initialization_files


def find_initialization_file(required: str, available: dict[str, str]) -> str | None:
    """
    This function finds an initialization file in the initialization folder.

    "<NAME>_results.h5" and "<NAME>.h5" stand for the same results, so a model file asking for one
    also accepts the other. The exact name is preferred. File names are compared without regard
    to case, as Windows does.

    Args:
        required (str): name of the initialization file asked for by the model file
        available (dict): {lower-case file name: file path} of the initialization folder

    Returns:
        str | None: path of the file found, or None if there is none
    """
    name = required.lower()
    candidates = [name]
    if name.endswith("_results.h5"):
        candidates.append(name.removesuffix("_results.h5") + ".h5")
    elif name.endswith(".h5"):
        candidates.append(name.removesuffix(".h5") + "_results.h5")
    for candidate in candidates:
        if candidate in available:
            return available[candidate]
    return None


def find_producer(required: str, dict_simulation: dict[str, str]) -> str | None:
    """
    This function finds the simulation in the input folder that produces an initialization file.

    "<NAME>_results.h5" and "<NAME>.h5" are both produced by "<NAME>_model.json". File names are
    compared without regard to case, as Windows does.

    Args:
        required (str): name of the initialization file
        dict_simulation (dict): {model file name: model file path} of the simulations to run

    Returns:
        str | None: model file name of the producing simulation, or None if there is none
    """
    models = {sim.lower(): sim for sim in dict_simulation}
    name = required.lower()
    for suffix in ["_results.h5", ".h5"]:
        if name.endswith(suffix):
            candidate = name.removesuffix(suffix) + "_model.json"
            if candidate in models:
                return models[candidate]
    return None


def resolve_initializations(
    dict_simulation: dict[str, str], initialization_files: dict[str, str]
) -> tuple[dict[str, set[str]], dict[str, str], dict[str, str]]:
    """
    This function resolves the initialization files required by the simulations.

    Each required file is looked up (file names compared without regard to case):
        1. in the initialization folder: the file is used as it is, "<NAME>_results.h5" and
           "<NAME>.h5" standing in for each other;
        2. in the input folder: "<NAME>_results.h5" or "<NAME>.h5" is produced by
           "<NAME>_model.json", which must then run before the simulations that need it;
        3. otherwise an error is raised.

    Args:
        dict_simulation (dict): {model file name: model file path} of the simulations to run
        initialization_files (dict): {file name: file path} of the initialization folder

    Returns:
        tuple: dependencies {model file name: set of model file names to run first},
               produced files {required file name: model file name that produces it}, and
               found files {required file name: file path in the initialization folder}
    """
    dependencies: dict[str, set[str]] = {sim: set() for sim in dict_simulation}
    produced: dict[str, str] = {}
    available = {name.lower(): filepath for name, filepath in initialization_files.items()}
    found: dict[str, str] = {}
    missing = []

    for sim, path in dict_simulation.items():
        for required in bt.initialization_files_from_json(path):
            filepath = find_initialization_file(required, available)
            if filepath is not None:
                if os.path.basename(filepath).lower() != required.lower():
                    logger.info(f"Initialization file {required} required by {sim}: using {os.path.basename(filepath)}")
                found[required] = filepath
                continue

            producer = find_producer(required, dict_simulation)

            if producer is None:
                missing.append((sim, required))
            elif producer == sim:
                logger.error(f"Simulation {sim} requires its own results {required} as initialization")
                raise Exception(f"Simulation {sim} requires its own results {required} as initialization")
            else:
                dependencies[sim].add(producer)
                produced[required] = producer

    if missing:
        for sim, required in missing:
            logger.error(f"Initialization file {required} required by {sim} not found")
        details = "; ".join(f"{sim} requires {required}" for sim, required in missing)
        raise FileNotFoundError(
            "Initialization files not found in the initialization folder, and no simulation in the input "
            f"folder produces them: {details}"
        )

    return dependencies, produced, found


def order_simulations(dict_simulation: dict[str, str], dependencies: dict[str, set[str]]) -> list[str]:
    """
    This function sorts the simulations so that every simulation comes after the ones it depends on.
    Among the simulations that can run, those that initialize other simulations come first.

    Args:
        dict_simulation (dict): {model file name: model file path} of the simulations to run
        dependencies (dict): {model file name: set of model file names to run first}

    Returns:
        list: model file names in running order

    Raises:
        Exception: if the dependencies are circular
    """
    n_dependents = {sim: 0 for sim in dict_simulation}
    for deps in dependencies.values():
        for dep in deps:
            n_dependents[dep] += 1

    order: list[str] = []
    done: set[str] = set()
    remaining = list(dict_simulation)
    while remaining:
        ready = [sim for sim in remaining if dependencies.get(sim, set()) <= done]
        if not ready:
            logger.error(f"Circular initialization dependencies between: {remaining}")
            raise Exception(f"Circular initialization dependencies between: {remaining}")
        ready.sort(key=lambda sim: -n_dependents[sim])  # stable: keeps the input order otherwise
        order.extend(ready)
        done.update(ready)
        remaining = [sim for sim in remaining if sim not in done]

    return order


@utils.timeit(logger, message_end="Simulation queue created in {elapsed:.2g} seconds")
def create_queue(paths: dict) -> dict:
    """
    This functions reads the scenarios to run.

    Args:
        paths (dict): dictionary containing the paths

    Returns:
        dict: dictionary containing the imported data
    """
    # Sorts the files to be imported
    simulations_to_run, paths["results_filepath"] = read_scenarios(paths["folder_input"])

    # Checks if all meshes are available
    meshes = read_meshes(paths["folder_meshes"])

    check_meshes(simulations_to_run, meshes)
    logger.info("All required meshes found")

    # Checks if the support files are available
    support_files = read_support_files(paths["folder_support"])

    # Resolves the initialization files: initialization folder first, then simulations in the input folder
    available_files = read_initialization_files(paths["folder_initialization"])
    dependencies, produced, initialization_files = resolve_initializations(simulations_to_run, available_files)
    order = order_simulations(simulations_to_run, dependencies)
    simulations_to_run = {sim: simulations_to_run[sim] for sim in order}
    if produced:
        logger.info(f"{len(produced)} initialization file(s) will be produced first: {sorted(produced)}")

    output = {
        "simulations_to_run": simulations_to_run,
        "meshes": meshes,
        "support_files": support_files,
        "initialization_files": initialization_files,
        "dependencies": dependencies,
        "produced": produced,
    }

    return output
