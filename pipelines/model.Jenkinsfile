pipeline {
    agent none
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 180, unit: 'MINUTES') }
    stages {
        stage('Ensure current source') {
            steps {
                // No executor held while waiting: also works on a one-executor controller.
                build job: 'nyc311-fetch', wait: true, propagate: true, parameters: [
                    string(name: 'APP_REPO_URL', value: params.APP_REPO_URL), string(name: 'APP_BRANCH', value: params.APP_BRANCH),
                    string(name: 'CONFIG_PATH', value: params.CONFIG_PATH), string(name: 'MONGO_DB_NAME', value: params.MONGO_DB_NAME),
                    string(name: 'NYC311_HOME', value: params.NYC311_HOME), string(name: 'PYTHON_BIN', value: params.PYTHON_BIN)]
            }
        }
        stage('Forecast and diagnostics') {
            agent { label 'nyc311-windows' }
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
                powershell '& .\scripts\runtime.ps1 -Action model -AppPath "$env:WORKSPACE\app"'
                script {
                    env.RESULT_RUN_ID = powershell(returnStdout: true, script: '(Get-Content app/artifacts/refresh-model.json -Raw | ConvertFrom-Json).prediction.run_id').trim()
                    env.APP_COMMIT = powershell(returnStdout: true, script: 'git -C app rev-parse HEAD').trim()
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
