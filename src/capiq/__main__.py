#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

# Libraries
import argparse
import logging
import sys
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


def main(user_opt, logger_filename: str | None = None) -> calculate_sim_queue.QueueOutcome:
    """Runs the queue; returns which simulations failed or were skipped, and capiQ's exit code."""
    logger = setup_logger(logger_filename)
    logger.info("Starting main function")

    overwrite = user_opt["simulation_options"].get("overwrite", False)
    paths = functions_io.setup_directories(overwrite=overwrite)

    # Stores the user options
    functions_io.write_user_options(user_opt, paths["folder_output"], logger)

    # Reads the scenarios to run
    simulations_to_run = create_sim_queue.create_queue(paths)

    # Runs the simulations
    # Annotated: the timing decorator hides calculate_queue's return type from mypy
    outcome: calculate_sim_queue.QueueOutcome = calculate_sim_queue.calculate_queue(simulations_to_run, paths, user_opt)

    logger.info("Main function finished")
    return outcome


def report(outcome: calculate_sim_queue.QueueOutcome) -> None:
    """Prints the simulations that did not run successfully, by reason, to the terminal."""
    groups = [
        (outcome.failed, "failed"),
        (outcome.blocked, "skipped because their initialization failed"),
        (outcome.already_complete, "skipped because an earlier run completed them"),
    ]
    for names, reason in groups:
        if names:
            listed = ", ".join(name.removesuffix("_model.json") for name in names)
            print(f"capiQ: {len(names)} simulation(s) {reason}: {listed}", file=sys.stderr)


# capiQ stopped with an error before or outside the simulations (e.g. empty input folder, missing mesh or
# initialization file, unreadable user_options.yml). Not 1: Python also exits with 1 on an uncaught error,
# and 1 means "some simulations were skipped because an earlier run completed them".
EXIT_ERROR = 3
# Stopped with Ctrl+C
EXIT_INTERRUPTED = 130


def run(argv: list[str] | None = None) -> int:
    """
    Command-line entry point: runs the queue and returns capiQ's exit code.

    0 every simulation ran and succeeded, 1 some were skipped because an earlier run completed them,
    2 a simulation failed (or was skipped because its initialization failed), 3 capiQ stopped with an
    error (EXIT_ERROR), 130 stopped with Ctrl+C.
    """
    parser = argparse.ArgumentParser(description="Run capiQ simulations.")
    parser.add_argument(
        "--logger-filename",
        type=str,
        default=None,
        help="Optional log filename. If omitted, a timestamped filename is used.",
    )
    args = parser.parse_args(argv)

    try:
        # Load configuration file
        with open("user_defined/user_options.yml") as file:
            user_opt = yaml.safe_load(file)

        outcome = main(user_opt, logger_filename=args.logger_filename)
    except KeyboardInterrupt:
        logging.getLogger("capiQ").warning("Interrupted by the user")
        print("\ncapiQ interrupted: running simulations were stopped", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as exc:
        # The full traceback goes to the log; the terminal gets the message
        logging.getLogger("capiQ").exception("capiQ stopped with an error")
        print(f"capiQ stopped with an error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    report(outcome)
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(run())
