# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Authors: Luiz E.D. de Oliveira, Mário J. Franca, Davide Vanzo
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)
# DOI: https://doi.org/10.5281/zenodo.24505637

"""capiQ: Computational Automation Pipeline for Hydro-morphodynamic simulation Queues.

Configures, manages and runs batches of BASEMENT simulations. Run it from the project root with ``python -m capiq``.
"""

from importlib.metadata import version

__version__ = version("capiQ")

__all__ = ["__version__"]
