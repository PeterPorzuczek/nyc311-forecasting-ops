pipeline {
    agent { label 'nyc311' }
    options { timestamps(); disableConcurrentBuilds(); skipDefaultCheckout(true); timeout(time: 120, unit: 'MINUTES') }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                dir('app') { checkout([$class: 'GitSCM', branches: [[name: params.APP_BRANCH]], userRemoteConfigs: [[url: params.APP_REPO_URL]]]) }
            }
        }
        stage('Fetch only when due') {
            steps { script { load('scripts/steps.groovy').runPython('-m scripts.runtime fetch --app-path app') } }
        }
    }
    post { always { archiveArtifacts artifacts: 'app/artifacts/refresh-fetch.json', allowEmptyArchive: true } }
}
