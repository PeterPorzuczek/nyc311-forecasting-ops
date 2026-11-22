"""Launch a hidden Windows service without inheriting Jenkins' open pipe handles."""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('python', 'script', 'config', 'cwd', 'log-dir'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--port', type=int, default=30130)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('This deployment launcher requires Windows')
    env = dict(os.environ, JENKINS_NODE_COOKIE='nyc311-frontend-service')
    logs = Path(args.log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'stdout.log').open('ab', buffering=0) as stdout, (logs / 'stderr.log').open('ab', buffering=0) as stderr:
        process = subprocess.Popen([args.python, args.script, '--config', args.config, '--port', str(args.port)],
            cwd=args.cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            close_fds=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    print(process.pid, flush=True)


if __name__ == '__main__':
    main()
