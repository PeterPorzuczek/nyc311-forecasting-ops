['fetch', 'model', 'front'].each { kind ->
    pipelineJob("nyc311-${kind}") {
        description("NYC311 ${kind}; managed by nyc311-seed. Configuration lives in the public ops repository.")
        logRotator { numToKeep(30); artifactNumToKeep(10) }
        parameters {
            stringParam('APP_REPO_URL', 'https://github.com/PeterPorzuczek/nyc311-forecasting.git', 'Public application repository')
            stringParam('APP_BRANCH', 'main', 'Application branch or commit')
            stringParam('CONFIG_PATH', 'config/production.json', 'Application configuration')
            stringParam('MONGO_DB_NAME', 'nyc311_forecasting', 'Existing local Mongo database')
            stringParam('NYC311_HOME', '', 'Persistent models, runs and runtime; empty uses the account data directory')
            stringParam('PYTHON_BIN', '', 'Python 3.12 executable; empty uses python3.12 or the py launcher')
            if (kind in ['fetch', 'model']) {
                choiceParam('TRAINING_POLICY', ['auto', 'reuse', 'train'], 'Reuse compatible artifact until its weekly refit is due')
                stringParam('RUN_ID', '', 'Empty: deterministic NYC business-day run ID')
                stringParam('SNAPSHOT_ID', '', 'Completed source snapshot passed by the preceding job')
            }
            if (kind == 'fetch') {
                choiceParam('FETCH_MODE', ['ingest', 'verify'], 'Ingest starts the chain; verify checks the completed model before frontend deployment')
            }
            if (kind in ['fetch', 'front']) {
                stringParam('EXPECTED_RUN_ID', '', 'Run that must be visible before deployment succeeds')
            }
        }
        if (kind == 'fetch') {
            triggers { cron('TZ=America/New_York\n0 10 * * *') }
        }
        definition {
            cpsScm {
                scm { git { remote { url('https://github.com/PeterPorzuczek/nyc311-forecasting-ops.git') }; branch('*/main') } }
                scriptPath("pipelines/${kind}.Jenkinsfile")
                lightweight(true)
            }
        }
    }
}
