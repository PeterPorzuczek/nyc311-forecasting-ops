#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    assert sys.argv[1:3] == ['-m', 'scripts.runtime']
    assert os.environ['MONGO_DB_NAME'].startswith('nyc311_test_')
    home = Path(os.environ['NYC311_HOME'])
    settings = json.loads((home / 'scenario.json').read_text())
    action = sys.argv[3]
    phase = os.environ['FETCH_MODE'] if action == 'fetch' else action
    app = Path(sys.argv[sys.argv.index('--app-path') + 1]).resolve()
    output = app / 'artifacts'
    output.mkdir(exist_ok=True)
    commit = subprocess.check_output(['git', '-C', str(app), 'rev-parse', 'HEAD'], text=True).strip()

    def event(state):
        with (home / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'phase': phase, 'state': state, 'time': time.time(),
                'job': os.environ['JOB_NAME'], 'build': os.environ['BUILD_NUMBER'],
                'branch': os.environ['APP_BRANCH'], 'snapshot': os.getenv('SNAPSHOT_ID'),
                'expected_run': os.getenv('EXPECTED_RUN_ID'), 'commit': commit}) + '\n')

    event('started')
    if phase == 'ingest' and settings.get('hold_ingest'):
        deadline = time.monotonic() + 120
        while not (home / 'release').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('Test did not release the delayed fetch')
            time.sleep(0.2)
    if phase == settings.get('fail_at'):
        event('failed')
        return 23
    snapshot = settings['snapshot']
    run_id = settings['run_id']
    if phase in ('model', 'verify'):
        assert os.environ['SNAPSHOT_ID'] == snapshot
    if phase == 'model':
        assert os.environ['RUN_ID'] == run_id
        result = {'prediction': {'run_id': run_id, 'snapshot_id': snapshot}}
        (output / 'refresh-model.json').write_text(json.dumps(result))
        (output / 'run-id.txt').write_text(run_id)
    if phase in ('verify', 'front'):
        assert os.environ['EXPECTED_RUN_ID'] == run_id
    if action == 'fetch':
        (output / 'refresh-fetch.json').write_text(json.dumps({'status': 'completed', 'snapshot_id': snapshot}))
        if phase == 'verify':
            (output / 'verification.json').write_text(json.dumps({'status': 'completed', 'forecast_run_id': run_id}))
    if phase == 'front':
        Path('artifacts').mkdir(exist_ok=True)
        Path('artifacts/frontend.json').write_text(json.dumps({'status': 'healthy', 'run_id': run_id}))
    else:
        (output / 'app-commit.txt').write_text(commit)
        (output / 'snapshot-id.txt').write_text(snapshot)
    event('completed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
