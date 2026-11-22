import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import textwrap

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
        args = p.parse_args()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                row = {'borough': 'QUEENS', 'complaint_type_group': 'OTHER', 'y_pred': 7}
                body = b'ok' if self.path == '/health' else json.dumps([
                    {'run_id': 'test', 'forecasts': [row], 'diagnostics': [row]}]).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
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


def test_reused_pid_is_rejected():
    process = psutil.Process()
    record = {'pid': process.pid, 'script': str(Path(process.cmdline()[1]).resolve()),
              'executable': process.exe(), 'created_at': process.create_time() - 10}
    with pytest.raises(RuntimeError):
        frontend.owned_process(record)
    assert process.is_running()


def test_frontend_survives_launcher_and_repeated_deployment(app, tmp_path, monkeypatch):
    home = tmp_path / 'home'
    output = tmp_path / 'ops'
    output.mkdir()
    (output / 'scripts').mkdir()
    (output / 'scripts/runtime.py').write_text('')
    (output / 'requirements.lock').write_text('')
    monkeypatch.setattr(frontend, 'ROOT', output)
    monkeypatch.setenv('MONGO_DB_NAME', 'nyc311_test_ops')
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
