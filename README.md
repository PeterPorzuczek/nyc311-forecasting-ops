# NYC311 forecasting — operations

Jenkins, scheduling and deployment for [nyc311-forecasting](https://github.com/PeterPorzuczek/nyc311-forecasting).
Application logic and model selection remain in the application repository.
The operations scripts use Python 3.12 on Linux, macOS and Windows. PowerShell is not required.

| Pipeline | Trigger | Result |
|---|---|---|
| `nyc311-fetch` | Daily 10:00 America/New_York; also requested by model | Complete current snapshot or certified no-op with zero API requests |
| `nyc311-model` | Daily 10:30 America/New_York or manual | Fetch check, forecasts, mature-label evaluation and diagnostics in Mongo; triggers frontend |
| `nyc311-front` | Successful model job or manual | Deploys the exact application commit and verifies the requested result |

The root `Jenkinsfile` generates these three jobs. It runs no application workload.
Schedules use New York time. The model job holds no executor while waiting for dependent jobs.
The node label is `nyc311`; it does not prescribe an operating system.

## Setup

See [SETUP.md](docs/SETUP.md). Install Python 3.12, Git, Jenkins and MongoDB.
The jobs must use the same host and account because MongoDB and the artifacts are local.
MongoDB remains `127.0.0.1:27017`, database `nyc311_forecasting`.
The frontend defaults to `127.0.0.1:30130`. For a public server, set the Jenkins node
environment variable `NYC311_FRONT_HOST=0.0.0.0` and forward its public port to 30130.
The bind address is part of deployment identity; health checks still use loopback.
Docker is not required for deployment.

SCM uses public HTTPS. Credentials and local configuration do not belong in Git.
Pipeline files and deployment scripts live only in this repository.

## Runtime

Set `NYC311_HOME` to a persistent directory outside the Jenkins workspace.
When empty, it uses `$XDG_DATA_HOME/nyc311` or `~/.local/share/nyc311` on POSIX systems,
and the account's `LocalAppData/nyc311` on Windows to preserve existing installations.

- `models` and `runs`: persistent artifacts referenced by MongoDB.
- `runtime/py312-<dependency hash>`: isolated environment with interprocess locking during installation.
- `front/releases/<application commit>`: committed files exported from Git, excluding uncommitted files.
- `front/process.json`, `stdout.log`, `stderr.log`: process identity and logs.

`scripts/runtime.py` prepares dependencies and calls the application's CLI.
`scripts/frontend.py` verifies PID, creation time, executable and script before stopping a process.
An unmanaged listener fails deployment. Repeated deployments with the same commit, configuration,
runtime and healthy process preserve its PID. A deployment lock serializes shared-host updates.
If a saved PID has been reused, its different creation time marks the record as stale;
deployment leaves that process untouched and can start the frontend when the port is free.
An occupied unmanaged port or a changed identity within the same process still blocks deployment.
The frontend starts in a separate session on POSIX and as a detached process on Windows.
Explicit standard streams and closed inherited handles let Jenkins finish while the frontend remains running.
Health, expected run, integer forecasts and matching diagnostic groups are checked before success.

The jobs preserve database contents and model history. Fetch checks completeness, maturity and source
revisions before skipping. The next business day performs bounded ingestion and correction.
The model uses the application's existing selection rules. After a reboot, Jenkins and MongoDB
must be running and the model/front job must be triggered to start the frontend.

## Parameters and local execution

Common: `APP_REPO_URL`, `APP_BRANCH`, `CONFIG_PATH`, `MONGO_DB_NAME`, `NYC311_HOME`, `PYTHON_BIN`.
`PYTHON_BIN` is an executable path; empty selects `python3.12` on POSIX or `py -3.12` on Windows.
Model: `TRAINING_POLICY` (`auto`, `reuse`, `train`) and optional `RUN_ID`.
Front: optional `EXPECTED_RUN_ID`, supplied automatically by the model job.
New parameters for an already completed immutable run require a new run ID.

```sh
python3.12 -m scripts.runtime fetch --app-path ../nyc311-forecasting
python3.12 -m scripts.runtime model --app-path ../nyc311-forecasting
python3.12 -m scripts.runtime front --app-path ../nyc311-forecasting
```

Jenkins uses `scripts/steps.groovy` to choose `sh` or `bat`.
Operations, locking and process management are implemented in Python.
Process inspection uses pinned `psutil`; environment setup uses the standard library.

## Verification

[Verification](docs/VERIFICATION.md) records actual runs and their limitations.
Ops tests exercise locks, committed releases, ownership checks, detached lifetime and repeated deployment.
Run with Python 3.12, `pytest` and the packages in `requirements.lock` installed:

```sh
python -m pytest -q
python -m ruff check .
```

The repository has fresh active Git history. Retired local metadata is ignored and was never published.

References: [Jenkins platform-specific execution](https://www.jenkins.io/doc/pipeline/tour/running-multiple-steps/),
[psutil process API](https://psutil.io/api/).
