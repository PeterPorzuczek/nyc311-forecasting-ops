pipeline {
    agent { label 'nyc311-windows' }
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 20, unit: 'MINUTES') }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
            }
        }
        stage('Deploy and verify frontend') {
            steps { powershell '& .\scripts\frontend.ps1 -AppPath "$env:WORKSPACE\app"' }
        }
    }
    post { always { archiveArtifacts artifacts: 'artifacts/frontend.json', allowEmptyArchive: true } }
}
