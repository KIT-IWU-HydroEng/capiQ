# Several CPU sockets or GPUs

On a machine with several CPU sockets, capiQ keeps each simulation inside one socket, on its own cores. Each GPU simulation gets its own card, plus one core on the socket that card is attached to. On a machine with a single socket nothing changes.

The log shows where each simulation starts.

## Options

In `user_defined/user_options.yml`, under `simulation_options`:

| Option | Meaning | Default |
| --- | --- | --- |
| `pin_to_socket` | Keep each simulation inside one CPU socket; GPU runs use a core on their card's socket. | `true` |
| `physical_cores_only` | One thread per physical core (skip hyper-thread siblings). | `true` |
| `gpu_numa_nodes` | Socket of each GPU, in `nvidia-smi` order. Only needed if auto-detection fails. | detected |

```yaml title="Two GPUs, the first on socket 0 and the second on socket 1"
simulation_options:
  parallel: true
  n_gpus: 2
  n_sim_cpus: 2
  n_sim_threads: 8
  pin_to_socket: true
  physical_cores_only: true
  gpu_numa_nodes: [0, 1]
```

## Check what capiQ detects

```bash
uv run python -c "from capiq import cpu_topology; cpu_topology.report()"
```

## Operating systems

=== "Windows"

    Tested on multi-socket hardware.

=== "Linux"

    Uses `numactl` if it is installed (`sudo apt-get install numactl`), otherwise `taskset`.

    !!! warning "Not tested on real multi-socket Linux hardware"
        Use it at your own risk, and set `pin_to_socket: false` if simulations fail or slow down.
