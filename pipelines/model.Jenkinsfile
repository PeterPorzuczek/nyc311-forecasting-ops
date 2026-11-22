pipeline {
    agent none
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 180, unit: 'MINUTES') }
    stages {
        stage('Ensure current source') {
            steps {
                build job: 'nyc311-fetch', wait: true, propagate: true, parameters: [
                    string(name: 'APP_REPO_URL', value: params.APP_REPO_URL), string(name: 'APP_BRANCH', value: params.APP_BRANCH),
                    string(name: 'CONFIG_PATH', value: params.CONFIG_PATH), string(name: 'MONGO_DB_NAME', value: params.MONGO_DB_NAME),
                    string(name: 'NYC311_HOME', value: params.NYC311_HOME), string(name: 'PYTHON_BIN', value: params.PYTHON_BIN)]
            }
        }
        stage('Forecast and diagnostics') {
            agent { label 'nyc311' }
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
                script {
                    load('scripts/steps.groovy').runPython('-m scripts.runtime model --app-path app')
                    env.RESULT_RUN_ID = readFile('app/artifacts/run-id.txt').trim()
                    env.APP_COMMIT = readFile('app/artifacts/app-commit.txt').trim()
                }
            }
            post { always { archiveArtifacts artifacts: 'app/artifacts/refresh-model.json', allowEmptyArchive: true } }
        }
        stage('Deploy frontend') {
            steps {
                build job: 'nyc311-front', wait: true, propagate: true, parameters: [
                    string(name: 'APP_REPO_URL', value: params.APP_REPO_URL), string(name: 'APP_BRANCH', value: env.APP_COMMIT),
                    string(name: 'CONFIG_PATH', value: params.CONFIG_PATH), string(name: 'MONGO_DB_NAME', value: params.MONGO_DB_NAME),
                    string(name: 'NYC311_HOME', value: params.NYC311_HOME), string(name: 'PYTHON_BIN', value: params.PYTHON_BIN),
                    string(name: 'EXPECTED_RUN_ID', value: env.RESULT_RUN_ID)]
            }
        }
    }
}
