# NYC311 forecasting — operations

Public operations repository for [nyc311-forecasting](https://github.com/PeterPorzuczek/nyc311-forecasting).
Application code, data contracts and model selection live in that repository.
This repository owns Jenkins, schedules and Windows frontend deployment.

| Pipeline | Trigger | Result |
|---|---|---|
| `nyc311-fetch` | Daily 10:00 America/New_York; also requested by model job | Complete current snapshot, or certified no-op with zero API requests |
| `nyc311-model` | Daily 10:30 America/New_York or manual | Checks fetch, forecasts, evaluates mature past forecasts, writes diagnostics and predictions to local Mongo; triggers frontend |
| `nyc311-front` | Successful model job or manual | Deploys exact application commit, verifies health and visibility of the requested prediction |

The root `Jenkinsfile` is the one-time/repeatable **seed job**, not a fourth business pipeline.
It generates the three jobs with an administrator-approved Job DSL script (approval is tied to its content).
Pipeline CPS remains sandboxed. Subsequent seed runs do not delete unrelated jobs.
Both cron expressions explicitly use New York time (normally 16:00/16:30 in Warsaw; DST transition weeks differ).

## Local setup

See [SETUP.md](docs/SETUP.md). Native Windows, Python 3.12, Git, Jenkins and MongoDB are required.
No Docker or cloud services are needed. MongoDB is `127.0.0.1:27017`, database `nyc311_forecasting`.
The frontend binds **only** `127.0.0.1:30130`.

SCM uses public HTTPS, so build agents do not need GitHub credentials. Jenkins credentials are never in this repository.
All pipeline files, deployment scripts and job definitions live here; there are no Jenkinsfiles in the application repository.

## Runtime and safety

`NYC311_HOME` defaults to `%LOCALAPPDATA%\nyc311` for the Jenkins account:

- `models` / `runs`: persistent artifacts referenced by Mongo; shared with local application runs.
- `runtime/py312-<requirements hash>`: isolated environment; installation serialized with a Windows mutex.
- `front/releases/<application commit>`: persistent frontend releases, independent of workspace cleanup.
- `front/process.json`, `stdout.log`, `stderr.log`: process identity and logs.

The jobs never clear/drop the database or delete model history. Fetch checks maturity, contiguous coverage,
snapshot date and live coverage revisions before skipping. Next-day fetch performs bounded corrections as well as new-day ingestion.
Partial data fails the build and prevents the model/front chain. Model selection remains an application responsibility;
`auto` reuses a compatible artifact until its weekly refit is due, then compares candidates on temporal validation.

The model pipeline holds no executor while waiting for another job, so one executor suffices.
Its frontend checkout is pinned to the commit that produced the prediction.
Deployment stops only a process whose PID, creation time, executable and script match its saved ownership record.
An unrelated listener causes a failure. Same-commit deployments keep the healthy process running.
`JENKINS_NODE_COOKIE` preserves the hidden service after the build. The Python launcher uses a detached process
and explicitly closes inherited handles, so Jenkins is not left waiting for its output pipes.
Health and prediction/diagnostic coverage are checked.
This starts the service after a successful model job; Windows reboot recovery requires Jenkins to be started again.

## Parameters

Common: `APP_REPO_URL`, `APP_BRANCH`, `CONFIG_PATH`, `MONGO_DB_NAME`, `NYC311_HOME`, `PYTHON_BIN`.
Empty `PYTHON_BIN` detects the local Python 3.12 install or `py -3.12`.
Model: `TRAINING_POLICY` (`auto` default), optional `RUN_ID` (default NYC business-day ID, safe retries).
To force a different policy or a second calculation on the same day, supply a new `RUN_ID`;
changing parameters of an existing immutable run is rejected.
Front: optional `EXPECTED_RUN_ID` (automatically supplied by model).
Changing application configuration requires compatible model artifacts or retraining; it does not rewrite prior runs.

## Layout

- `Jenkinsfile`: seed pipeline.
- `jobs/nyc311.groovy`: job names, parameters, cron and SCM definitions.
- `pipelines/*.Jenkinsfile`: the three execution pipelines.
- `scripts/runtime.ps1`: dependency setup and application command adapter.
- `scripts/frontend.ps1`: owned-process deployment and HTTP verification.
- `scripts/detach_frontend.py`: hidden launch with isolated standard streams and handle inheritance.
- `scripts/configure_jenkins.py`: repeatable API setup of the seed job.

This repository starts with fresh Git history. Prior local Git metadata was retired outside active history
and is ignored; it is not part of any public commit. No upstream private repository is modified.

## Verified execution

See [the actual local Jenkins verification](docs/VERIFICATION.md): successful complete chains,
zero-request fetch, preserved source data, 36 integer forecasts and diagnostics, and a frontend
that survives build completion. The JSON evidence includes schedules, build numbers and plugin versions.
