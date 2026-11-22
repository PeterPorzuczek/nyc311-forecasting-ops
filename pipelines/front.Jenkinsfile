pipeline {
    agent { label 'nyc311' }
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 20, unit: 'MINUTES') }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
            }
        }
        stage('Deploy and verify frontend') {
            steps { script { load('scripts/steps.groovy').runPython('-m scripts.runtime front --app-path app') } }
        }
    }
    post { always { archiveArtifacts artifacts: 'artifacts/frontend.json', allowEmptyArchive: true } }
}
