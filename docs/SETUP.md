# Local setup

1. Run MongoDB on `127.0.0.1:27017` and preserve `nyc311_forecasting`.
2. Install Python 3.12 and Git. Run Jenkins under an account with access to the existing
   models and reports. Set `NYC311_HOME` when using a nondefault location.
3. Install Jenkins Pipeline, Git, Job DSL and Timestamper with compatible dependencies.
4. Assign label `nyc311` to one local node. All jobs need the same local MongoDB and artifact directory.
   Linux, macOS and Windows nodes use the same pipeline definitions.
5. Create a Pipeline from SCM seed named `nyc311-seed`, repository
   `https://github.com/PeterPorzuczek/nyc311-forecasting-ops.git`, branch `*/main`, script `Jenkinsfile`.
   Alternatively supply `JENKINS_USER` and `JENKINS_TOKEN` in the environment and run:

```sh
python3.12 scripts/configure_jenkins.py --url http://127.0.0.1:8080 --build
```

6. Run the seed and approve exactly the reviewed `jobs/nyc311.groovy` source in Jenkins Script Approval.
   Rerun the seed after approval. A changed DSL source requires its own approval.
   Pipeline sandboxing, CSRF protection and unrelated jobs remain unchanged.
7. Run `nyc311-fetch` with `FETCH_MODE=ingest`. On success it triggers model, then a
   verification fetch, then frontend. Only the first fetch has a 10:00 New York cron.
   Rerun the seed when upgrading to remove the former 10:30 model cron.
   Inspect archived JSON and open [local results](http://127.0.0.1:30130/).

An API token is preferred for the setup helper. Password authentication uses a session crumb.
Never save credentials in source, job parameters or remote URLs.
On POSIX the default interpreter is `python3.12`; set `PYTHON_BIN` to an absolute executable path if needed.
On Windows the fallback is `py -3.12`; no PowerShell installation or scripts are used.

For an empty database, perform the application's documented backfill before scheduled refresh.
A current, unchanged, complete snapshot returns `already_current`, `api_requests: 0`, `fetched: 0`.
A stale or revised snapshot must be refreshed.

Deployment recognizes the previous process record format and verifies ownership before replacement.
An unmanaged service on port 30130 is never stopped automatically.
The persistent home must be shared by successive builds and kept outside workspaces.

References: [Pipeline syntax](https://www.jenkins.io/doc/book/pipeline/syntax/),
[remote API](https://www.jenkins.io/doc/book/using/remote-access-api/),
[Job DSL](https://plugins.jenkins.io/job-dsl/).
