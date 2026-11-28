pipeline {
    agent { label 'nyc311' }
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 120, unit: 'MINUTES') }
    stages {
        stage('Validate chain inputs') {
            steps { script {
                if (!(params.FETCH_MODE in ['ingest', 'verify'])) { error('FETCH_MODE must be ingest or verify') }
                if (params.FETCH_MODE == 'verify' && (!params.SNAPSHOT_ID?.trim() || !params.EXPECTED_RUN_ID?.trim())) {
                    error('Verification requires SNAPSHOT_ID and EXPECTED_RUN_ID from the successful model job')
                }
            } }
        }
        stage('Checkout') {
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
            }
        }
        stage('Fetch and verify when requested') {
            steps { script { load('scripts/steps.groovy').runPython('-m scripts.runtime fetch --app-path app') } }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'app/artifacts/refresh-fetch.json,app/artifacts/verification.json', allowEmptyArchive: true }
        success { script {
            def common = [
                string(name: 'APP_REPO_URL', value: params.APP_REPO_URL),
                string(name: 'APP_BRANCH', value: readFile('app/artifacts/app-commit.txt').trim()),
                string(name: 'CONFIG_PATH', value: params.CONFIG_PATH), string(name: 'MONGO_DB_NAME', value: params.MONGO_DB_NAME),
                string(name: 'NYC311_HOME', value: params.NYC311_HOME), string(name: 'PYTHON_BIN', value: params.PYTHON_BIN)]
            if (params.FETCH_MODE == 'ingest') {
                build job: 'nyc311-model', wait: false, quietPeriod: 0, parameters: common + [
                    string(name: 'SNAPSHOT_ID', value: readFile('app/artifacts/snapshot-id.txt').trim()),
                    string(name: 'TRAINING_POLICY', value: params.TRAINING_POLICY), string(name: 'RUN_ID', value: params.RUN_ID)]
            } else {
                build job: 'nyc311-front', wait: false, quietPeriod: 0, parameters: common + [
                    string(name: 'EXPECTED_RUN_ID', value: params.EXPECTED_RUN_ID)]
            }
        } }
    }
}
