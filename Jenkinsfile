pipeline {
    agent { label 'nyc311-windows' }

    options {
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 10, unit: 'MINUTES')
    }

    stages {
        stage('Checkout seed repository') {
            steps {
                checkout scm
            }
        }

        stage('Generate Jenkins jobs') {
            steps {
                jobDsl(
                    targets: 'jobs/*.groovy',
                    removedJobAction: 'IGNORE',
                    removedViewAction: 'IGNORE',
                    lookupStrategy: 'JENKINS_ROOT',
                    sandbox: true,
                )
            }
        }
    }
}
