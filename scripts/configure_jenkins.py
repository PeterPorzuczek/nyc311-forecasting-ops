import argparse
import base64
from http.cookiejar import CookieJar
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request
from xml.sax.saxutils import escape


def main():
    p = argparse.ArgumentParser(description='Configure the NYC311 Jenkins seed job')
    p.add_argument('--url', default='http://127.0.0.1:8080')
    p.add_argument('--build', action='store_true')
    args = p.parse_args()
    secret = os.environ['JENKINS_TOKEN']
    user = os.environ.get('JENKINS_USER', 'admin')
    auth = base64.b64encode(f'{user}:{secret}'.encode()).decode()
    headers = {'Authorization': 'Basic ' + auth}
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    def request(path, data=None, content_type=None):
        current = dict(headers)
        if content_type:
            current['Content-Type'] = content_type
        return opener.open(Request(args.url.rstrip('/') + path, data=data, headers=current), timeout=30)
    with request('/crumbIssuer/api/json') as response:
        crumb = json.load(response)
    headers[crumb['crumbRequestField']] = crumb['crumb']
    repo = escape('https://github.com/PeterPorzuczek/nyc311-forecasting-ops.git')
    config = f'''<flow-definition plugin="workflow-job">
      <description>NYC311 ops seed: creates exactly three application pipelines from reviewed Job DSL.</description>
      <keepDependencies>false</keepDependencies><properties/>
      <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
        <scm class="hudson.plugins.git.GitSCM" plugin="git"><configVersion>2</configVersion>
          <userRemoteConfigs><hudson.plugins.git.UserRemoteConfig><url>{repo}</url></hudson.plugins.git.UserRemoteConfig></userRemoteConfigs>
          <branches><hudson.plugins.git.BranchSpec><name>*/main</name></hudson.plugins.git.BranchSpec></branches>
          <doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations><submoduleCfg class="empty-list"/><extensions/>
        </scm><scriptPath>Jenkinsfile</scriptPath><lightweight>true</lightweight>
      </definition><triggers/><disabled>false</disabled>
    </flow-definition>'''.encode()
    try:
        request('/job/nyc311-seed/api/json').close()
        path = '/job/nyc311-seed/config.xml'
    except HTTPError as exc:
        if exc.code != 404:
            raise
        path = '/createItem?' + urlencode({'name': 'nyc311-seed'})
    request(path, config, 'application/xml').close()
    print('Configured', args.url.rstrip('/') + '/job/nyc311-seed/')
    if args.build:
        response = request('/job/nyc311-seed/build', b'')
        print('Queued seed:', response.headers.get('Location', 'accepted'))
        response.close()


if __name__ == '__main__':
    main()
