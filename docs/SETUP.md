# Windows / localhost setup

1. Start native MongoDB on `127.0.0.1:27017`. Preserve the existing `nyc311_forecasting` database.
2. Run Jenkins under the same Windows account that owns `%LOCALAPPDATA%\nyc311`, or configure `NYC311_HOME`
   and grant that account access to the existing models/runs. Install Python 3.12 and Git.
3. Install Jenkins plugins Pipeline, Git, Job DSL and Timestamper. Restart when dependencies require it.
4. Assign label `nyc311-windows` to the local node. This local setup intentionally uses the controller's existing executors.
5. Create a Pipeline from SCM seed named `nyc311-seed`:
   `https://github.com/PeterPorzuczek/nyc311-forecasting-ops.git`, branch `*/main`, script `Jenkinsfile`.
   Alternatively set `JENKINS_USER` and `JENKINS_TOKEN` in the process environment and run
   `python scripts/configure_jenkins.py --url http://127.0.0.1:8080 --build`.
   An API token is preferred. Password authentication also works with the session crumb used by this helper.
   Never put a secret in source code, a build parameter or a Git remote URL.
6. Run seed, then `nyc311-model`. The chain is fetch → model → front. Check archived JSON and console status.
7. Open [local results](http://127.0.0.1:30130/) and the diagnostics section.

An existing manually launched viewer must be stopped once after verifying its executable, script and port.
The deployment refuses to kill unmanaged processes. Later deployments manage only their recorded process identity.

No initial backfill is performed automatically. For a new empty database, run the documented application backfill first.
For the already imported database, the first fetch must report `already_current`, `api_requests: 0`, `fetched: 0`.
Missing, changed or previous-day snapshots deliberately do not qualify for that shortcut.

The jobs are additive and preserve all other Jenkins projects. Security, CSRF protection and the Groovy sandbox remain enabled.

Primary references: [Jenkins Pipeline syntax](https://www.jenkins.io/doc/book/pipeline/syntax/),
[remote API](https://www.jenkins.io/doc/book/using/remote-access-api/),
[CSRF protection](https://www.jenkins.io/doc/book/security/csrf-protection/),
[Job DSL](https://plugins.jenkins.io/job-dsl/).
