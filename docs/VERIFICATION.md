# Jenkins and portability verification

## Update — 28 November 2026: sequential trigger chain

The independent model timer has been removed. Only fetch is scheduled at 10:00
America/New_York. The successful initial fetch queues model; successful model queues
fetch in verification mode; successful verification queues frontend.

The actual Job DSL and all three Jenkinsfiles were executed on the remote Linux
controller in an isolated test folder, with one executor. Applying the former DSL
and then the new DSL removed the old model cron. The controller's Declarative
validator accepted fetch, model and front.

| Scenario | Observed phases | Result |
|---|---|---|
| Deliberately delayed fetch | ingest → model → verify → front | Model stayed unstarted until fetch was released and succeeded |
| Initial fetch failure | ingest | No model, verification or frontend |
| Model failure | ingest → model | No verification or frontend |
| Verification failure | ingest → model → verify | No frontend |

The Jenkins runs used `tests/jenkins_fixture.py` as their application process, a
reserved test database name and separate artifact homes. They exercised real SCM
checkouts, parameters, job queues and success/failure triggers without reimporting
production data or restarting the public frontend. The fixture checked propagation
of snapshot ID, forecast run ID and the exact application commit. This is orchestration
evidence, not a production model benchmark.

Separately, all **91 application tests** passed against native MongoDB on Windows,
without skips, including the real CLI pipeline and forecast verification. All
**15 operations tests** and Ruff passed locally and on Ubuntu and Windows in
[GitHub Actions](https://github.com/PeterPorzuczek/nyc311-forecasting-ops/actions/runs/46133165325).
Verification checks source freshness/completeness, snapshot and dataset lineage,
completed publication, forecast/diagnostic group coverage and integer forecast totals.

Incident review: on 27 November the initial remote fetch #4 ran from 15:00:00 to
15:50:55 UTC. Model job #3 was scheduled at 15:30 but its calculation waited for
its dependency fetch #5 and began after 15:51. The old schedule therefore started
the job too early, while the existing dependency prevented modeling before fetch
completed in that observed run. The new explicit chain removes the independent timer.

Earlier sections below record the former configuration and are historical evidence.

## Update — 23 November 2026, Europe/Warsaw

The active operations code uses Python, with `sh`/`bat` dispatch in Jenkins.
There are no PowerShell scripts or source comments in either repository.
The node label is `nyc311`. Setup, fetch, model and frontend definitions passed
the controller's Declarative Pipeline validator.

| Job | Build | Result |
|---|---:|---|
| nyc311-seed | 4 | SUCCESS |
| nyc311-fetch | 5 | SUCCESS |
| nyc311-model | 6 | SUCCESS |
| nyc311-front | 5, 6, 7 | SUCCESS |

Model #6 completed the entire fetch → model → front chain. Front #6 deployed
application `f0f6e4ecc3b67dfc9fdea7d67d860b9cdaed1eaf`; #7 repeated deployment,
returned `already_running=true` and preserved listener PID 16560.
Health and the expected run remained available after build completion.
Fetch made **0 API requests** and fetched **0 records**. Source collections retained
2,021,898 documents each. All 72 forecast documents matched their pre-run checksum.
The frontend exposes 36 forecasts and 36 diagnostics for the production run.

Application tests with native MongoDB passed **72 tests**, without skips.
Operations tests passed **6 tests locally**, then the same **6 tests on Ubuntu and
6 on Windows** in [GitHub Actions](https://github.com/PeterPorzuczek/nyc311-forecasting-ops/actions/runs/45081510495).
Ruff passed in each environment. Tests exercise interprocess locks, committed-file
exports, process ownership, detached lifetime, repeat deployment and refusal to
stop an unmanaged listener. macOS was not executed; the full application MongoDB
integration suite was executed on the local Windows host.

The source audit found zero Python comments/docstrings across 55 application files
and 4 ops files, zero Groovy comments and zero `.ps1` files.
Exact records: [portable_verification_20261123.json](results/portable_verification_20261123.json).

## Original local verification — 22 November 2026

Verified against the running Windows controller at `http://127.0.0.1:8080` and native
MongoDB at `127.0.0.1:27017`, database `nyc311_forecasting`. Full machine-readable
evidence: [local_verification_20261122.json](results/local_verification_20261122.json).

## Actual builds

| Job | Verified build | Result | Trigger |
|---|---:|---|---|
| nyc311-seed | 3 | SUCCESS | Setup from public ops SCM |
| nyc311-fetch | 4 | SUCCESS | Model dependency; daily cron also configured |
| nyc311-model | 5 | SUCCESS | Manual end-to-end verification; daily cron also configured |
| nyc311-front | 3 and 4 | SUCCESS | Model #5 triggered #3; #4 verified final JSON encoding |

Two consecutive complete chains succeeded: model #4 → front #2 and model #5 → front #3.
The final frontend-only check #4 also succeeded. Earlier failures remain in Jenkins
history and were fixed, rather than relabeled as successful builds.

Schedules read back from the actual job configuration:

- Fetch: `TZ=America/New_York`, `0 10 * * *`.
- Model: `TZ=America/New_York`, `30 10 * * *`.
- Front: no independent cron; waits for successful model publication.

All three pipeline files also passed the controller's Declarative Pipeline validator.
SCM URLs point to the two new **public** `PeterPorzuczek/nyc311-forecasting*` repositories.
The deployed application revision is `4ebafa263c6e24af411cf83f7132c94703893ae7`.
Jenkins orchestration and deployment scripts exist only in this ops repository.

## Data and model checks

- First successful fetch (#2), and all later fetches, returned `already_current`,
  **api_requests=0**, **fetched=0**. Initial setup failures occurred before source access.
- `raw_current`, `raw_history`, `snapshot_rows` each contain **2,021,898** documents,
  unchanged from before the Jenkins run. No application data was deleted.
- Snapshot is unchanged, through **2026-11-20**, with **184 mature days** and **36 groups**.
- `nyc311-model-20261122`: **36 integer predictions**, **36 diagnostic documents**,
  target **2026-11-23**, total **12,654**, selected model **weekday_mean4**.
- The production comparison reproduced the frozen development scores exactly:
  seasonal naive **48.103836**, weekday mean4 **38.716931**, tuned CatBoost MAE **38.890873**.
- Repeating the complete chain left all prediction documents byte-equivalent under
  canonical BSON JSON serialization (including their issue timestamps and write metadata).
  SHA-256: `7265499c4213d5c192b1fe74d8d7b8f9c245378aa1b44508791fb6a7e175fc7c`.
- Forecast evaluations correctly wait for mature future labels.

## Frontend checks

`http://127.0.0.1:30130/health` returned HTTP 200 after the jobs had finished.
The results API returned the requested completed run, 36 integer forecasts and 36 diagnostics.
Browser verification confirmed the total, run filter and expanded history diagnostics.
The service remained alive after build completion. Repeated deployment reported
`already_running=true` and preserved the listener PID; unrelated processes were not stopped.

## Fixes found by execution

1. Installed Job DSL and updated incompatible older Pipeline dependencies. The old
   workflow-job plugin failed during build finalization with missing `TarArchiveInputStream`.
   Plugin versions actually used are recorded in the JSON evidence. Existing unrelated jobs were retained.
2. Approved exactly the reviewed Job DSL source by its content; global script security and CSRF stay enabled.
3. Corrected Groovy/PowerShell path escaping and restored Windows PowerShell module discovery
   when the controller inherited a PowerShell 7 module path.
4. Replaced a launcher that leaked inherited Jenkins pipe handles with a hidden detached
   Python process, explicit standard streams and `close_fds=True`.
5. Published frontend JSON as UTF-8 without BOM, so ordinary HTTP JSON consumers can read it.
6. Application tests uncovered transient Windows access errors during atomic JSON replacement.
   Bounded retries preserve atomicity and still fail on persistent permission errors.

The application's final native-Mongo test suite passed **72 tests**, with no skips;
Ruff passed. This verification exercised a real current-data no-op and real model/deployment
execution. It did not advance the system clock or download tomorrow's data to simulate a cron event.
Next-day invalidation, incomplete coverage and revised-data rejection are covered by application tests.
Schedules require the machine, MongoDB and Jenkins to remain running.
