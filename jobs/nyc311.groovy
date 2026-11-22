// Exactly three application jobs. The root Jenkinsfile is the setup/seed job.
['fetch', 'model', 'front'].each { kind ->
    pipelineJob("nyc311-${kind}") {
        description("NYC311 ${kind}; managed by nyc311-seed. Configuration lives in the public ops repository.")
        logRotator { numToKeep(30); artifactNumToKeep(10) }
        parameters {
            stringParam('APP_REPO_URL', 'https://github.com/PeterPorzuczek/nyc311-forecasting.git', 'Public application repository')
            stringParam('APP_BRANCH', 'main', 'Application branch or commit')
            stringParam('CONFIG_PATH', 'config/production.json', 'Application configuration')
            stringParam('MONGO_DB_NAME', 'nyc311_forecasting', 'Existing local Mongo database')
            stringParam('NYC311_HOME', '', 'Empty: LocalAppData/nyc311; shared persistent models, runs and runtime')
            stringParam('PYTHON_BIN', '', 'Empty: local Python 3.12 installation or py launcher')
            if (kind == 'model') {
                choiceParam('TRAINING_POLICY', ['auto', 'reuse', 'train'], 'Reuse compatible artifact until its weekly refit is due')
                stringParam('RUN_ID', '', 'Empty: deterministic NYC business-day run ID')
            }
            if (kind == 'front') {
                stringParam('EXPECTED_RUN_ID', '', 'Run that must be visible before deployment succeeds')
            }
        }
        if (kind != 'front') {
            triggers { cron("TZ=America/New_York\n${kind == 'fetch' ? '0 10' : '30 10'} * * *") }
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
