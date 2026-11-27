# capiQ — Computational Automation Pipeline for Hydro-morphodynamic simulation Queues

<p align="center">
  <a href="https://github.com/KIT-IWU-HydroEng/capiQ/actions/workflows/ci.yml"><img src="https://github.com/KIT-IWU-HydroEng/capiQ/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://kit-iwu-hydroeng.github.io/capiQ/"><img src="https://github.com/KIT-IWU-HydroEng/capiQ/actions/workflows/docs.yml/badge.svg" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/python-3.11--3.14-blue" alt="Python 3.11 to 3.14">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://github.com/KIT-IWU-HydroEng/capiQ/releases/latest"><img src="https://img.shields.io/github/v/release/KIT-IWU-HydroEng/capiQ" alt="Latest release"></a>
  <a href="https://github.com/KIT-IWU-HydroEng/capiQ/commits/main"><img src="https://img.shields.io/github/last-commit/KIT-IWU-HydroEng/capiQ" alt="Last commit"></a>
  <a href="https://doi.org/10.5281/zenodo.24505637"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.24505637.svg" alt="DOI"></a>
</p>

capiQ is a Python-based Computational Automation Pipeline for Hydro-morphodynamic simulation Queues, designed to configure, manage, and execute large simulation batches efficiently. It runs [BASEMENT](https://basement.ethz.ch) 4.x simulations in parallel on CPUs and GPUs, chains simulations that start from each other's results, and resumes interrupted queues.



## Documentation

**Available at: <https://kit-iwu-hydroeng.github.io/capiQ/>**

- **Getting started:** [installation](https://kit-iwu-hydroeng.github.io/capiQ/getting-started/installation/) · [quick start](https://kit-iwu-hydroeng.github.io/capiQ/getting-started/quickstart/)
- **User guide:** [configuration](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/configuration/) · [input files](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/input-files/) · [running capiQ](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/running/) · [outputs](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/outputs/) · [initialization simulations](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/initialization/) · [resuming a queue](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/resuming/) · [several CPU sockets or GPUs](https://kit-iwu-hydroeng.github.io/capiQ/user-guide/multi-socket-gpu/)
- **[Examples](https://kit-iwu-hydroeng.github.io/capiQ/examples/)**
- **[Developer reference](https://kit-iwu-hydroeng.github.io/capiQ/reference/overview/)**

To browse the documentation offline, run `uv sync` once, then `uv run zensical serve -f docs/zensical.toml` from the project root and open `http://localhost:8000`.

## Supported hydrodynamic software

- BASEMENT 4.x [[1]](#1)[[2]](#2)

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, the checks and tests, managing dependencies with uv, working on the documentation, and the commit and pull request conventions.

## Citation

If you use this software in your research, please cite it as described in [CITATION.cff](CITATION.cff) (GitHub shows a *Cite this repository* button). Each release is archived on Zenodo: [10.5281/zenodo.24505637](https://doi.org/10.5281/zenodo.24505637) always points to the latest version, and the Zenodo page lists the DOI of each version.

## References

<a id="1">[1]</a>
Vanzo, D., Peter, S., Vonwiller, L., Bürgler, M., Weberndorfer, M., Siviglia, A., Conde, D., Vetsch, D.F., 2021. basement v3: A modular freeware for river process modelling over multiple computational backends. Environmental Modelling & Software 143, 105102. https://doi.org/10.1016/j.envsoft.2021.105102

<a id="2">[2]</a>
Vetsch, D.F., Frei, S., Halso, M.C., Schierjott, J.C., Bürgler, M., Vanzo, D., 2024. Basement V4—A Multipurpose Modelling Environment for Simulation of Flood Hazards and River Morphodynamics Across Scales, in: Gourbesville, P., Caignaert, G. (Eds.), Advances in Hydroinformatics—SimHydro 2023 Volume 1. Springer Nature, Singapore, pp. 125–138. https://doi.org/10.1007/978-981-97-4072-7_8
