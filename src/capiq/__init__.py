# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

"""capiQ: Computational Automation Pipeline for Hydro-morphodynamic simulation Queues.

Configures, manages and runs batches of BASEMENT simulations. Run it from the project root with ``python -m capiq``.
"""

from importlib.metadata import version

__version__ = version("capiQ")

__all__ = ["__version__"]
