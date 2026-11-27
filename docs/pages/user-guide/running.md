# Running capiQ

## From the project root

capiQ looks for `user_defined/` in the current folder, so start it from the project root:

```bash
uv run python -m capiq
```

Without uv, run `python -m capiq` with the virtual environment activated.

## With the launcher scripts

The launchers change to the project root by themselves, so they can be started from anywhere (or with a double click on Windows):

=== "Windows"

    ```powershell
    run_capiQ.bat
    ```

=== "Linux and macOS"

    ```bash
    ./run_capiQ.sh
    ```

They use uv if it is installed, and otherwise the `.venv` virtual environment in the project root (capiQ must then be installed in it, see [Installation without uv](../getting-started/installation.md#without-uv)).

## Command-line options

Options are passed on by the launchers too.

| Option | Meaning |
| --- | --- |
| `--logger-filename NAME` | Name of the log file. Default: `capiQ_YYYY-MM-DD_HH-MM.log` in the project root. |

```bash
uv run python -m capiq --logger-filename river_run1.log
```

## What happens during a run

```mermaid
flowchart TD
    %% Links are relative to this page's URL; the build does not check links inside a chart
    S1["<b>1.</b>#nbsp;Read#nbsp;user_options.yml"]
    S2["<b>2.</b>#nbsp;Build#nbsp;the#nbsp;queue,#nbsp;initialization#nbsp;simulations#nbsp;first#nbsp;(<a href='../initialization/'>initialization#nbsp;files</a>)"]
    S1 --> S2

    subgraph each ["For each simulation, in parallel on CPUs and GPUs"]
        direction TB
        S3{"<b>3.</b> Earlier results<br/>in output/?<br/>(<a href='../resuming/'>Resuming#nbsp;a#nbsp;queue</a>)"}
        SKIP["Skip"]
        CONT["Continue from<br/>the last output"]
        FULL["<b>4.</b> BASEMENT<br/>setup, simulation,<br/>results<br/>(<a href='../configuration/#run-options-user_optionsyml'>user_options.yml</a>)"]
        RES["Results<br/>step only"]
        S5["<b>5.</b> Progress bar<br/>and log"]
        S3 -- "complete" --> SKIP
        S3 -- "partial<br/>(<a href='../resuming/#partial-simulations-are-continued'>Resuming#nbsp;a#nbsp;queue</a>)" --> CONT
        S3 -- "none or unusable" --> FULL
        S3 -- "complete, no .xdmf" --> RES
        CONT --> S5
        FULL --> S5
        RES --> S5
    end

    S2 --> S3
    SKIP --> S6
    S5 --> S6["<b>6.</b>#nbsp;Report#nbsp;failed#nbsp;and#nbsp;skipped#nbsp;simulations,#nbsp;exit#nbsp;with#nbsp;an#nbsp;exit#nbsp;code#nbsp;(<a href='#exit-codes'>exit#nbsp;codes</a>)"]
```

## Exit codes

The exit code tells scripts and job schedulers how the queue went, without reading the log:

| Code | Meaning |
| --- | --- |
| `0` | Every simulation ran in this run and succeeded. |
| `1` | Nothing failed, but some simulations were skipped because an earlier run had already completed them (see [Resuming a queue](resuming.md)). |
| `2` | At least one simulation failed, or was skipped because its [initialization simulation](initialization.md) failed. This takes precedence over `1`. |
| `3` | capiQ stopped with an error before or outside the simulations, e.g. an empty `input/`, a missing mesh or initialization file, or an unreadable `user_options.yml`. The message is printed in the terminal, and the full error is in the log. The launcher scripts also return `3` when they find neither uv nor `.venv`. |
| `130` | Stopped with ++ctrl+c++. |

For example, when one simulation fails and three were completed by an earlier run, capiQ prints:

```text
capiQ: 1 simulation(s) failed: SCENARIO_Q002
capiQ: 3 simulation(s) skipped because an earlier run completed them: SCENARIO2_Q001, SCENARIO2_Q002, SCENARIO_Q001
```

and exits with `2`. With an empty `input/`, it stops before running anything and prints the error with the expected folder layout:

```text
capiQ stopped with an error: The input folder …\input is empty.
Add the files, then run capiQ again. The following layout is expected:
...
```

and exits with `3`. The launcher scripts pass the exit code on. To check it after a run:

=== "Windows (PowerShell)"

    ```powershell
    uv run python -m capiq
    echo $LASTEXITCODE
    ```

=== "Linux and macOS"

    ```bash
    uv run python -m capiq
    echo $?
    ```

## Stopping a run

Press ++ctrl+c++. capiQ stops the queue together with the running BASEMENT processes and exits with `130`. Start it again to continue where it stopped: see [Resuming a queue](resuming.md).
