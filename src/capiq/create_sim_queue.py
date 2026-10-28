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

    output = {"simulations_to_run": simulations_to_run, "meshes": meshes, "support_files": support_files}

    return output
