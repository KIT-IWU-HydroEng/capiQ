# Configuration

capiQ reads two files in `user_defined/`:

- `constants.py`: where things are on your computer (BASEMENT, meshes, support files, initialization files).
- `user_options.yml`: how the queue runs (parallel or sequential, CPU and GPU processes, outputs).

Both are plain text files: edit them before running capiQ.

## Paths: `constants.py`

| Constant | Meaning | Default |
| --- | --- | --- |
| `BASEMENT_PATH` | Folder with the BASEMENT executables (`BMv4_setup`, `BMv4_BASEHPC_*`, …). | `C:\Program Files\BASEMENT 4.3.0\bin` on Windows, `/usr/bin` on Linux |
| `MESH_FOLDER` | Folder with the `.2dm` mesh files. | `example_files/meshes` |
| `SUPPORT_FOLDER` | Folder with the discharge `.txt` files named in the model files. | `example_files/support_files` |
| `INITIALIZATION_FOLDER` | Folder with results files used as initial conditions (optional, see [Initialization simulations](initialization.md)). | `example_files/initialization` |

`PROJECT_ROOT` is the repository folder; use it to build paths relative to the project, or give full paths:

```python
MESH_FOLDER = PROJECT_ROOT / "my_project" / "meshes"
SUPPORT_FOLDER = pathlib.Path(r"D:\data\river\discharges")
```

??? example "The default `user_defined/constants.py`"

    ```python
    --8<-- "user_defined/constants.py"
    ```

!!! warning
    Do not commit personal paths in `constants.py` if you contribute to capiQ.

## Run options: `user_options.yml`

### General

| Option | Meaning | Default if missing |
| --- | --- | --- |
| `store_configs` | Keep each simulation's `_model.json` as BASEMENT read it (with the full paths of its files) and a copy of its `_simulation.json` next to its results. `false` leaves them out. The files in `input/` are never changed. | `true` |
| `output_subfolders` | One folder per simulation (`output/NAME/`). `false` writes all files directly in `output/`. See [Outputs](outputs.md). | `true` |

### `simulation_options`

| Option | Meaning | Default if missing |
| --- | --- | --- |
| `parallel` | `true`: run several simulations at the same time on the CPU and GPU processes below. `false`: run them one after the other on the CPU. | `false` |
| `n_sim_cpus` | Number of simulations that run at the same time on the CPU (parallel mode). | `1` |
| `n_sim_threads` | Threads of each CPU simulation (BASEMENT's OpenMP backend). | number of logical cores |
| `n_gpus` | Number of simulations that run at the same time on GPUs (parallel mode), one per card. | `0` |
| `gpu_backend` | BASEMENT backend for GPU runs: `cuda` or `cudaC`. | `cudaC` |
| `preferred_device` | Which device takes the next simulation when a GPU and a CPU process are both free: `gpu` or `cpu`. | `gpu` |
| `pin_to_socket` | On machines with several CPU sockets, keep each simulation inside one socket. See [Several CPU sockets or GPUs](multi-socket-gpu.md). | `true` |
| `physical_cores_only` | One thread per physical core, skipping hyper-thread siblings. | `true` |
| `gpu_numa_nodes` | Socket of each GPU in `nvidia-smi` order, only when auto-detection fails, e.g. `[0, 1]`. | detected |
| `overwrite` | Delete `output/` at the start and run every simulation from scratch. See [Resuming a queue](resuming.md). | `false` |
| `verbose` | Also write BASEMENT's full output into the capiQ log (it is always in the per-simulation logs). | `false` |

??? example "The default `user_defined/user_options.yml`"

    ```yaml
    --8<-- "user_defined/user_options.yml"
    ```

### Typical setups

=== "Sequential, CPU"

    ```yaml
    simulation_options:
      parallel: false
      n_sim_threads: 8        # all simulations use 8 threads, one after the other
    ```

=== "Several CPU runs at once"

    ```yaml
    simulation_options:
      parallel: true
      n_gpus: 0
      n_sim_cpus: 4           # 4 simulations at the same time ...
      n_sim_threads: 4        # ... with 4 threads each (16 cores)
    ```

=== "GPUs plus CPU"

    ```yaml
    simulation_options:
      parallel: true
      gpu_backend: cudaC
      n_gpus: 2               # one simulation per card
      n_sim_cpus: 1           # and one on the CPU
      n_sim_threads: 8
      preferred_device: gpu   # a free GPU gets the next simulation first
    ```

The options are copied to `output/capiQ_user_options.json` and to the log at the start of each run, so you can see later which settings produced the results.
