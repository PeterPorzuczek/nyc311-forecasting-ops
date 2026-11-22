import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import venv


ROOT = Path(__file__).resolve().parents[1]


def home_dir():
    if os.environ.get('NYC311_HOME'):
        return Path(os.environ['NYC311_HOME']).expanduser().resolve()
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        return Path(os.environ['LOCALAPPDATA']) / 'nyc311'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'nyc311'


def python_in(directory):
    return Path(directory) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def inside(directory, relative):
    directory = Path(directory).resolve()
    result = (directory / relative).resolve()
    if not result.is_relative_to(directory) or result == directory:
        raise ValueError('Path must stay inside its application directory')
    return result


@contextmanager
def exclusive_lock(path, timeout=600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Timed out acquiring deployment lock') from None
                time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def environment(home):
    env = dict(os.environ)
    database = env.get('MONGO_DB_NAME') or 'nyc311_forecasting'
    if not re.fullmatch(r'nyc311_[A-Za-z0-9_]+', database):
        raise ValueError('Expected an explicitly named NYC311 database')
    env.update(MONGO_URI='mongodb://127.0.0.1:27017', MONGO_DB_NAME=database,
               MODEL_ARTIFACT_DIR=str(home / 'models'), RUN_ARTIFACT_DIR=str(home / 'runs'),
               PYTHONUNBUFFERED='1', PYTHONUTF8='1')
    return env


def prepare(app):
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Python 3.12 required')
    app = Path(app).resolve()
    config = inside(app, os.environ.get('CONFIG_PATH') or 'config/production.json')
    if not config.is_file():
        raise FileNotFoundError('Missing application configuration')
    home = home_dir()
    env = environment(home)
    dependency_hash = hashlib.sha256((app / 'requirements.lock').read_bytes()
                                    + (ROOT / 'requirements.lock').read_bytes()).hexdigest()
    directory = home / 'runtime' / f'py312-{dependency_hash[:16]}'
    python = python_in(directory)
    with exclusive_lock(home / 'runtime' / 'setup.lock'):
        ready = directory / '.ready'
        if not ready.is_file() or ready.read_text() != dependency_hash or not python.is_file():
            venv.EnvBuilder(with_pip=True).create(directory)
            subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                            '-r', str(app / 'requirements.lock'), '-r', str(ROOT / 'requirements.lock')], check=True)
            subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
            ready.write_text(dependency_hash, encoding='utf-8')
    return python, home, config, env


def main():
    parser = argparse.ArgumentParser(description='Prepare runtime and run NYC311 operations')
    parser.add_argument('action', choices=['prepare', 'fetch', 'model', 'front'])
    parser.add_argument('--app-path', required=True, type=Path)
    args = parser.parse_args()
    app = args.app_path.resolve()
    python, home, config, env = prepare(app)
    if args.action == 'prepare':
        print(json.dumps({'python': str(python), 'home': str(home)}))
    elif args.action == 'front':
        subprocess.run([str(python), '-m', 'scripts.frontend', '--app-path', str(app),
                        '--home', str(home), '--config', str(config.relative_to(app))],
                       cwd=ROOT, env=env, check=True)
    else:
        output = app / 'artifacts' / f'refresh-{args.action}.json'
        command = [str(python), 'main_refresh.py', args.action, '--config', str(config), '--output', str(output)]
        if args.action == 'model':
            for key, option in [('TRAINING_POLICY', '--training-policy'), ('RUN_ID', '--run-id')]:
                if env.get(key):
                    command.extend([option, env[key]])
        subprocess.run(command, cwd=app, env=env, check=True)
        if args.action == 'model':
            result = json.loads(output.read_text(encoding='utf-8'))
            (output.parent / 'run-id.txt').write_text(result['prediction']['run_id'], encoding='utf-8')
            commit = subprocess.check_output(['git', '-C', str(app), 'rev-parse', 'HEAD'], text=True).strip()
            (output.parent / 'app-commit.txt').write_text(commit, encoding='utf-8')


if __name__ == '__main__':
    main()
