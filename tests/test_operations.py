import json
from datetime import datetime, timezone
import os
import socket
import subprocess
import sys
import textwrap
from unittest.mock import Mock

import psutil
import pytest

from scripts import frontend, runtime


def git(app, *args):
    return subprocess.check_output(['git', '-C', str(app), *args], text=True).strip()


@pytest.fixture
def app(tmp_path):
    root = tmp_path / 'app with spaces'
    (root / 'presentation').mkdir(parents=True)
    (root / 'config').mkdir()
    (root / 'config/production.json').write_text('{}')
    (root / 'presentation/app.py').write_text(textwrap.dedent('''
        import argparse
        import json
        from http.server import BaseHTTPRequestHandler, HTTPServer
        p = argparse.ArgumentParser()
        p.add_argument('--config')
        p.add_argument('--port', type=int)
        p.add_argument('--host', default='127.0.0.1')
        args = p.parse_args()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                row = {'borough': 'QUEENS', 'complaint_type_group': 'OTHER', 'y_pred': 7}
                body = b'ok' if self.path == '/health' else json.dumps([
                    {'run_id': 'test', 'forecasts': [row], 'diagnostics': [row]}]).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        HTTPServer((args.host, args.port), Handler).serve_forever()
    '''), encoding='utf-8')
    git(root, 'init')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
    return root


def test_config_cannot_escape_checkout(tmp_path):
    with pytest.raises(ValueError, match='inside'):
        runtime.inside(tmp_path, '../outside.json')


def test_database_guard_and_platform_home(tmp_path, monkeypatch):
    monkeypatch.setenv('MONGO_DB_NAME', 'unrelated')
    with pytest.raises(ValueError, match='database'):
        runtime.environment(tmp_path)
    monkeypatch.setenv('MONGO_DB_NAME', 'nyc311_test_ops')
    assert runtime.environment(tmp_path)['MODEL_ARTIFACT_DIR'] == str(tmp_path / 'models')
    monkeypatch.setenv('NYC311_HOME', str(tmp_path))
    assert runtime.home_dir() == tmp_path


def test_lock_serializes_processes_and_releases(tmp_path):
    lock = tmp_path / 'setup.lock'
    program = 'from scripts.runtime import exclusive_lock\nimport sys\nwith exclusive_lock(sys.argv[1], .2): pass'
    with runtime.exclusive_lock(lock):
        result = subprocess.run([sys.executable, '-c', program, str(lock)], cwd=runtime.ROOT, capture_output=True)
        assert result.returncode != 0
        assert b'Timed out acquiring' in result.stderr
    subprocess.run([sys.executable, '-c', program, str(lock)], cwd=runtime.ROOT, check=True)


def test_release_contains_only_committed_content(app, tmp_path):
    (app / 'config/production.json').write_text('{"dirty": true}')
    (app / '.env').write_text('LOCAL_ONLY=true')
    commit, release = frontend.release_from_git(app, tmp_path / 'home')
    assert release.name == commit
    assert (release / 'config/production.json').read_text() == '{}'
    assert not (release / '.env').exists()


@pytest.mark.parametrize('iso_timestamp', [False, True])
def test_reused_pid_is_ignored_before_inspecting_unrelated_process(monkeypatch, tmp_path, iso_timestamp):
    process = Mock(pid=123)
    process.create_time.return_value = 1700000010.0
    process.cmdline.side_effect = psutil.AccessDenied(process.pid)
    process.exe.side_effect = psutil.AccessDenied(process.pid)
    monkeypatch.setattr(frontend.psutil, 'Process', lambda pid: process)
    created_at = 1700000000.0
    if iso_timestamp:
        created_at = datetime.fromtimestamp(created_at, timezone.utc).isoformat().replace('+00:00', 'Z')
    record = {'pid': process.pid, 'script': str(tmp_path / 'app.py'),
              'executable': sys.executable, 'created_at': created_at}
    assert frontend.owned_process(record) is None
    frontend.stop_owned([record, record])
    process.cmdline.assert_not_called()
    process.exe.assert_not_called()
    process.terminate.assert_not_called()


@pytest.mark.parametrize('mismatch', ['script', 'executable'])
def test_same_process_with_changed_identity_is_not_stopped(monkeypatch, tmp_path, mismatch):
    script = str(tmp_path / 'app.py')
    process = Mock(pid=123)
    process.create_time.return_value = 1700000000.0
    process.cmdline.return_value = [sys.executable, script if mismatch != 'script' else str(tmp_path / 'other.py')]
    process.exe.return_value = sys.executable if mismatch != 'executable' else str(tmp_path / 'other-python')
    monkeypatch.setattr(frontend.psutil, 'Process', lambda pid: process)
    record = {'pid': process.pid, 'script': script, 'executable': sys.executable,
              'created_at': process.create_time()}
    with pytest.raises(RuntimeError, match='identity|ownership'):
        frontend.stop_owned([record])
    process.terminate.assert_not_called()


@pytest.mark.parametrize('occupied_port', [False, True])
def test_deploy_recovers_stale_state_without_stopping_reused_pid(app, tmp_path, monkeypatch, occupied_port):
    home = tmp_path / 'home'
    output = tmp_path / 'ops'
    (output / 'scripts').mkdir(parents=True)
    (output / 'scripts/runtime.py').write_text('')
    (output / 'requirements.lock').write_text('')
    monkeypatch.setattr(frontend, 'ROOT', output)
    monkeypatch.setenv('MONGO_DB_NAME', 'nyc311_test_ops')
    commit, release = frontend.release_from_git(app, home)
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)'], **options)
    state = None
    try:
        record = {'pid': unrelated.pid, 'created_at': psutil.Process(unrelated.pid).create_time() - 60,
                  'executable': sys.executable, 'script': str(release / 'presentation/app.py')}
        frontend.write_json(home / 'front/process.json', {'commit': commit, 'launcher': record, 'listener': record})
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            if occupied_port:
                sock.listen()
                with pytest.raises(RuntimeError, match='unmanaged'):
                    frontend.deploy(app, home, 'config/production.json', 'test', port)
                assert json.loads((home / 'front/process.json').read_text())['listener'] == record
        if not occupied_port:
            report = frontend.deploy(app, home, 'config/production.json', 'test', port)
            state = json.loads((home / 'front/process.json').read_text())
            assert report['status'] == 'healthy'
            assert report['already_running'] is False
            assert state['listener']['pid'] != unrelated.pid
            assert frontend.deploy(app, home, 'config/production.json', 'test', port)['already_running'] is True
        assert unrelated.poll() is None
    finally:
        if state:
            frontend.stop_owned([state['listener'], state['launcher']])
        unrelated.terminate()
        unrelated.wait(timeout=15)


@pytest.mark.parametrize('host', ['127.0.0.1', '0.0.0.0'])
def test_frontend_survives_launcher_and_repeated_deployment(app, tmp_path, monkeypatch, host):
    home = tmp_path / 'home'
    output = tmp_path / 'ops'
    output.mkdir()
    (output / 'scripts').mkdir()
    (output / 'scripts/runtime.py').write_text('')
    (output / 'requirements.lock').write_text('')
    monkeypatch.setattr(frontend, 'ROOT', output)
    monkeypatch.setenv('MONGO_DB_NAME', 'nyc311_test_ops')
    monkeypatch.setenv('NYC311_FRONT_HOST', host)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    child_code = ('from pathlib import Path\nfrom scripts import frontend\nimport sys\n'
                  'frontend.ROOT = Path(sys.argv[4])\n'
                  'frontend.deploy(Path(sys.argv[1]), Path(sys.argv[2]), "config/production.json", "test", int(sys.argv[3]))')
    env = dict(os.environ, MONGO_DB_NAME='nyc311_test_ops')
    state = None
    try:
        subprocess.run([sys.executable, '-c', child_code, str(app), str(home), str(port), str(output)],
                       cwd=runtime.ROOT, env=env, capture_output=True, check=True, timeout=45)
        state = json.loads((home / 'front/process.json').read_text())
        assert frontend.verify('test', port)['forecasts'] == 1
        report = frontend.deploy(app, home, 'config/production.json', 'test', port)
        assert report['already_running'] is True
        assert report['host'] == host
        assert state['host'] == host
        listener = psutil.Process(state['listener']['pid'])
        assert any(c.status == psutil.CONN_LISTEN and c.laddr.ip == host and c.laddr.port == port
                   for c in listener.net_connections(kind='tcp'))
        assert report['listener_pid'] == state['listener']['pid']
        with pytest.raises(RuntimeError, match='Expected completed prediction'):
            frontend.verify('missing', port)
        (home / 'front/process.json').unlink()
        with pytest.raises(RuntimeError, match='unmanaged'):
            frontend.deploy(app, home, 'config/production.json', 'test', port)
        assert frontend.listening(port)
    finally:
        if state:
            frontend.stop_owned([state['listener'], state['launcher']])
