#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

# Libraries
import argparse
import logging
import time

import yaml

from capiq import (
    calculate_sim_queue,
    create_sim_queue,
    functions_io,
)


def setup_logger(logger_filename: str | None = None) -> logging.Logger:
    if logger_filename is None:
        timestamp = time.strftime("%Y-%m-%d_%H-%M")
        log_filename = f"capiQ_{timestamp}.log"
    else:
        log_filename = logger_filename

    logging.basicConfig(
        filename=log_filename, level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    return logging.getLogger("capiQ")


def main(user_opt, logger_filename: str | None = None) -> None:
    logger = setup_logger(logger_filename)
    logger.info("Starting main function")

    overwrite = user_opt["simulation_options"].get("overwrite", False)
    paths = functions_io.setup_directories(overwrite=overwrite)

    # Stores the user options
    functions_io.write_user_options(user_opt, paths["folder_output"], logger)

    # Reads the scenarios to run
    simulations_to_run = create_sim_queue.create_queue(paths)

    # Runs the simulations
    calculate_sim_queue.calculate_queue(simulations_to_run, paths, user_opt)

    logger.info("Main function finished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run capiQ simulations.")
    parser.add_argument(
        "--logger-filename",
        type=str,
        default=None,
        help="Optional log filename. If omitted, a timestamped filename is used.",
    )
    args = parser.parse_args()

    # Load configuration file
    with open("user_defined/user_options.yml") as file:
        user_opt = yaml.safe_load(file)

    main(user_opt, logger_filename=args.logger_filename)
