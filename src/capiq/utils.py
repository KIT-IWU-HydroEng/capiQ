#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

if __name__ == "__main__":
    raise Exception("This file must be run as module")

# Libraries
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
