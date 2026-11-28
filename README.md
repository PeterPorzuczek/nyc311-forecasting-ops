# NYC311 forecasting — operations

Jenkins, scheduling and deployment for [nyc311-forecasting](https://github.com/PeterPorzuczek/nyc311-forecasting).
Application logic and model selection remain in the application repository.
The operations scripts use Python 3.12 on Linux, macOS and Windows. PowerShell is not required.

| Pipeline | Trigger | Result |
|---|---|---|
| `nyc311-fetch` (`ingest`) | Daily 10:00 America/New_York or manual | Complete source snapshot; triggers model on success |
| `nyc311-model` | Successful ingest fetch | Forecast and diagnostics using that exact snapshot; triggers verification fetch on success |
| `nyc311-fetch` (`verify`) | Successful model | Checks source freshness, snapshot lineage, forecast publication and diagnostics; triggers frontend on success |
| `nyc311-front` | Successful verification fetch | Deploys the exact application commit and verifies the requested result |

The root `Jenkinsfile` generates these three jobs. It runs no application workload.
Only the initial fetch has a schedule, in New York time. Every transition runs in
`post { success { ... } }` and queues the next job without waiting for it. Each job
reports its own result; a failed or aborted job cannot start the following step.
The verification fetch terminates at frontend and never triggers another model.
This forward chain works with one executor and `disableConcurrentBuilds()` on fetch.
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
Start the complete chain with `nyc311-fetch`, `FETCH_MODE=ingest`. It accepts
`TRAINING_POLICY` (`auto`, `reuse`, `train`) and optional model `RUN_ID`.
The successful fetch passes `SNAPSHOT_ID` and the exact application commit to model.
Model passes these identifiers plus `EXPECTED_RUN_ID` to fetch in `verify` mode.
The second fetch uses the ordinary freshness check: a current source is a no-op;
outdated data is fetched. A changed snapshot or incomplete publication blocks frontend
and requires restarting the chain with a new model run ID. It never silently substitutes
a newer dataset for the model's original source. Provisional labels retain the application's
existing admission policy; verification does not declare future actuals available.
Starting the model Jenkins job without `SNAPSHOT_ID` fails with instructions to start fetch.
Front receives `EXPECTED_RUN_ID` only after verification succeeds.
New parameters for an already completed immutable run require a new run ID.

```sh
python3.12 -m scripts.runtime fetch --app-path ../nyc311-forecasting
python3.12 -m scripts.runtime model --app-path ../nyc311-forecasting
python3.12 -m scripts.runtime front --app-path ../nyc311-forecasting
```

These local CLI commands run individual stages; Jenkins performs the trigger chain.
After updating both application and ops revisions, rerun `nyc311-seed` so the old model
cron is removed and new parameters are installed. Do not update only the pipeline files
while leaving the former job configuration in place.

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
