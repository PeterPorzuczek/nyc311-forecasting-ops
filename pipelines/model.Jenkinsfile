pipeline {
    agent { label 'nyc311' }
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 180, unit: 'MINUTES') }
    stages {
        stage('Require completed upstream fetch') {
            steps { script {
                if (!params.SNAPSHOT_ID?.trim()) { error('Start nyc311-fetch in ingest mode; model requires its completed SNAPSHOT_ID') }
            } }
        }
        stage('Checkout') {
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
            }
        }
        stage('Forecast and diagnostics') {
            steps { script { load('scripts/steps.groovy').runPython('-m scripts.runtime model --app-path app') } }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'app/artifacts/refresh-model.json', allowEmptyArchive: true }
        success { script {
            build job: 'nyc311-fetch', wait: false, quietPeriod: 0, parameters: [
                string(name: 'APP_REPO_URL', value: params.APP_REPO_URL),
                string(name: 'APP_BRANCH', value: readFile('app/artifacts/app-commit.txt').trim()),
                string(name: 'CONFIG_PATH', value: params.CONFIG_PATH), string(name: 'MONGO_DB_NAME', value: params.MONGO_DB_NAME),
                string(name: 'NYC311_HOME', value: params.NYC311_HOME), string(name: 'PYTHON_BIN', value: params.PYTHON_BIN),
                string(name: 'FETCH_MODE', value: 'verify'),
                string(name: 'SNAPSHOT_ID', value: readFile('app/artifacts/snapshot-id.txt').trim()),
                string(name: 'EXPECTED_RUN_ID', value: readFile('app/artifacts/run-id.txt').trim())]
        } }
    }
}
