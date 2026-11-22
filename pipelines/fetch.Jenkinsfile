pipeline {
    agent { label 'nyc311-windows' }
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 120, unit: 'MINUTES') }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
            }
        }
        stage('Fetch only when due') {
            steps { powershell '& ./scripts/runtime.ps1 -Action fetch -AppPath "$env:WORKSPACE/app"' }
        }
    }
    post { always { archiveArtifacts artifacts: 'app/artifacts/refresh-fetch.json', allowEmptyArchive: true } }
}
