import argparse
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import urlopen
import zipfile

import psutil

from scripts.runtime import ROOT, exclusive_lock, inside


PORT = 30130


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2)
        temporary = Path(stream.name)
    try:
        for attempt in range(6):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * 2 ** attempt)
    finally:
        temporary.unlink(missing_ok=True)


def listening(port=PORT):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) == 0


def process_record(process, script):
    if str(Path(script).resolve()) not in [str(Path(arg).resolve()) for arg in process.cmdline()[1:] if not arg.startswith('--')]:
        raise RuntimeError('Unexpected frontend script identity')
    return {'pid': process.pid, 'created_at': process.create_time(), 'executable': process.exe(), 'script': str(script)}


def owned_process(record):
    try:
        process = psutil.Process(record['pid'])
        expected_time = record['created_at']
        if isinstance(expected_time, str):
            expected_time = datetime.fromisoformat(expected_time.replace('Z', '+00:00')).timestamp()
        current = process_record(process, record['script'])
        if abs(current['created_at'] - expected_time) > 0.0001 or Path(current['executable']) != Path(record['executable']):
            raise RuntimeError('Process ownership changed; refusing to stop an unrelated process')
        return process
    except psutil.NoSuchProcess:
        return None


def has_listener(process, port=PORT):
    return any(c.status == psutil.CONN_LISTEN and c.laddr.ip == '127.0.0.1' and c.laddr.port == port
               for c in process.net_connections(kind='tcp'))


def stop_owned(records):
    processes = {}
    for record in records:
        process = owned_process(record)
        if process:
            processes[process.pid] = process
    for process in processes.values():
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(list(processes.values()), timeout=15)
    if alive:
        raise RuntimeError('Previous frontend did not stop')


def release_from_git(app, home):
    commit = subprocess.check_output(['git', '-C', str(app), 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise RuntimeError('Cannot determine application revision')
    releases = home / 'front' / 'releases'
    releases.mkdir(parents=True, exist_ok=True)
    release = releases / commit
    if not release.is_dir():
        archive = subprocess.check_output(['git', '-C', str(app), 'archive', '--format=zip', commit])
        with tempfile.TemporaryDirectory(dir=releases) as temporary:
            stage = Path(temporary) / 'release'
            stage.mkdir()
            with zipfile.ZipFile(io.BytesIO(archive)) as source:
                for member in source.infolist():
                    destination = inside(stage, member.filename)
                    if (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Symlinks are not supported in frontend releases')
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(source.read(member))
            stage.rename(release)
    return commit, release


def launch(python, script, config, release, front_home, port=PORT):
    env = dict(os.environ, JENKINS_NODE_COOKIE='nyc311-frontend-service', BUILD_ID='nyc311-frontend-service')
    options = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    with (front_home / 'stdout.log').open('ab', buffering=0) as stdout, (front_home / 'stderr.log').open('ab', buffering=0) as stderr:
        process = subprocess.Popen([str(python), str(script), '--config', str(config), '--port', str(port)],
            cwd=release, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True, **options)
    owner = psutil.Process(process.pid)
    launcher = process_record(owner, script)
    try:
        for _ in range(300):
            if process.poll() is not None:
                raise RuntimeError('Frontend exited; inspect persistent stderr.log')
            for candidate in [owner, *owner.children(recursive=True)]:
                try:
                    if has_listener(candidate, port):
                        return {'launcher': launcher, 'listener': process_record(candidate, script)}
                except psutil.NoSuchProcess:
                    continue
            time.sleep(0.1)
        raise TimeoutError('Frontend did not start listening')
    except BaseException:
        records = [launcher]
        for child in owner.children(recursive=True):
            records.append(process_record(child, script))
        stop_owned(records)
        raise


def verify(expected_run, port=PORT):
    url = f'http://127.0.0.1:{port}'
    with urlopen(url + '/health', timeout=10) as response:
        if response.status != 200:
            raise RuntimeError('Frontend healthcheck failed')
    query = urlencode({'run_id': expected_run} if expected_run else {'limit': 1})
    with urlopen(url + '/api/prediction-results?' + query, timeout=20) as response:
        runs = json.load(response)
    if not runs or (expected_run and runs[0]['run_id'] != expected_run):
        raise RuntimeError('Expected completed prediction is not visible')
    result = runs[0]
    forecasts = {(r['borough'], r['complaint_type_group']) for r in result['forecasts']}
    diagnostics = {(r['borough'], r['complaint_type_group']) for r in result['diagnostics']}
    if not forecasts or forecasts != diagnostics or len(forecasts) != len(result['forecasts']):
        raise RuntimeError('Forecast/diagnostic coverage mismatch')
    if not all(type(r['y_pred']) is int and r['y_pred'] >= 0 for r in result['forecasts']):
        raise RuntimeError('Expected nonnegative integer forecasts')
    return {'status': 'healthy', 'url': url, 'run_id': result['run_id'],
            'forecasts': len(forecasts), 'diagnostics': len(diagnostics)}


def deploy(app, home, config, expected_run=None, port=PORT):
    front_home = home / 'front'
    front_home.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(front_home / 'deploy.lock'):
        commit, release = release_from_git(app, home)
        config_path = inside(release, config)
        if not config_path.is_file():
            raise FileNotFoundError('Configuration is missing from the committed release')
        script = release / 'presentation' / 'app.py'
        version = hashlib.sha256(Path(__file__).read_bytes() + (ROOT / 'scripts/runtime.py').read_bytes()
                                 + (ROOT / 'requirements.lock').read_bytes()).hexdigest()
        identity = {'commit': commit, 'database': os.environ['MONGO_DB_NAME'], 'deployment_version': version,
                    'python': str(Path(sys.executable).resolve()), 'config': str(config)}
        state_path = front_home / 'process.json'
        state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.exists() else None
        same = False
        if listening(port):
            process = owned_process(state['listener']) if state else None
            if not process or not has_listener(process, port):
                raise RuntimeError('Frontend port is owned by an unmanaged service; no process was stopped')
            same = all(state.get(key) == value for key, value in identity.items())
        if not same:
            if state:
                stop_owned([state['listener'], state['launcher']])
            if listening(port):
                raise RuntimeError('Frontend port is still occupied; no new process was started')
            state = {**identity, **launch(sys.executable, script, config_path, release, front_home, port)}
            write_json(state_path, state)
        report = {**verify(expected_run, port), 'commit': commit, 'already_running': same, 'listener_pid': state['listener']['pid']}
        write_json(ROOT / 'artifacts/frontend.json', report)
        return report


def main():
    parser = argparse.ArgumentParser(description='Deploy the committed frontend and verify its results')
    parser.add_argument('--app-path', required=True, type=Path)
    parser.add_argument('--home', required=True, type=Path)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    print(json.dumps(deploy(args.app_path.resolve(), args.home.resolve(), args.config, os.environ.get('EXPECTED_RUN_ID'))))


if __name__ == '__main__':
    main()
