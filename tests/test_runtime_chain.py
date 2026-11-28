import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import runtime


@pytest.mark.parametrize('failed_check', [False, True])
def test_post_model_fetch_checks_after_refresh_and_propagates_failure(tmp_path, monkeypatch, failed_check):
    app = tmp_path / 'app'
    app.mkdir()
    output = app / 'artifacts'
    output.mkdir()
    config = app / 'config.json'
    config.write_text('{}')
    env = {'FETCH_MODE': 'verify', 'SNAPSHOT_ID': 'source-snapshot', 'EXPECTED_RUN_ID': 'model-run'}
    monkeypatch.setattr(runtime, 'prepare', lambda path: (Path(sys.executable), tmp_path, config, env))
    monkeypatch.setattr(sys, 'argv', ['runtime', 'fetch', '--app-path', str(app)])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['check'] is True
        if command[2] == 'fetch':
            (output / 'refresh-fetch.json').write_text(json.dumps({'snapshot_id': 'source-snapshot'}))
        else:
            assert command[2] == 'verify'
            assert command[command.index('--snapshot-id') + 1] == 'source-snapshot'
            assert command[command.index('--forecast-run-id') + 1] == 'model-run'
            if failed_check:
                raise subprocess.CalledProcessError(4, command)

    monkeypatch.setattr(runtime.subprocess, 'run', run)
    monkeypatch.setattr(runtime.subprocess, 'check_output', lambda *args, **kwargs: 'a' * 40)
    if failed_check:
        with pytest.raises(subprocess.CalledProcessError):
            runtime.main()
        assert not (output / 'app-commit.txt').exists()
    else:
        runtime.main()
        assert (output / 'snapshot-id.txt').read_text() == 'source-snapshot'
    assert [command[2] for command in calls] == ['fetch', 'verify']


def test_model_receives_the_snapshot_from_upstream(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    app.mkdir()
    output = app / 'artifacts'
    output.mkdir()
    config = app / 'config.json'
    config.write_text('{}')
    env = {'SNAPSHOT_ID': 'upstream-snapshot', 'RUN_ID': 'requested-run', 'TRAINING_POLICY': 'reuse'}
    monkeypatch.setattr(runtime, 'prepare', lambda path: (Path(sys.executable), tmp_path, config, env))
    monkeypatch.setattr(sys, 'argv', ['runtime', 'model', '--app-path', str(app)])

    def run(command, **kwargs):
        assert command[command.index('--snapshot-id') + 1] == env['SNAPSHOT_ID']
        assert command[command.index('--run-id') + 1] == env['RUN_ID']
        (output / 'refresh-model.json').write_text(json.dumps({'prediction': {
            'run_id': 'requested-run', 'snapshot_id': 'upstream-snapshot'}}))

    monkeypatch.setattr(runtime.subprocess, 'run', run)
    monkeypatch.setattr(runtime.subprocess, 'check_output', lambda *args, **kwargs: 'a' * 40)
    runtime.main()
    assert (output / 'run-id.txt').read_text() == 'requested-run'
    assert (output / 'snapshot-id.txt').read_text() == 'upstream-snapshot'
