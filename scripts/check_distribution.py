"""Read-only source distribution policy audit; not a legal or secret-content scan."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DIRS = {'data', 'outputs', 'runs', 'tools', 'spikes', 'tasks', '.venv', 'build', 'dist'}
NATIVE_SUFFIXES = {'.uasset', '.uexp', '.ubulk', '.umap', '.pak', '.utoc', '.ucas'}


def restricted(path: str) -> bool:
    """Conservative filename policy; no file bytes are changed or uploaded."""
    p = PurePosixPath(path.replace('\\', '/'))
    name = p.name.lower()
    return (
        bool(p.parts and p.parts[0].lower() in LOCAL_DIRS)
        or name == 'handoff.md'
        or name == '.env' or (name.startswith('.env.') and name != '.env.example')
        or name.endswith('.db') or '.db-' in name or '.db.' in name
        or '.sqlite' in name
        or p.suffix.lower() in NATIVE_SUFFIXES
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, help='scan an unpacked source archive instead of the Git index')
    args = parser.parse_args(argv)
    if args.directory is not None:
        directory = args.directory.resolve()
        if not directory.is_dir():
            parser.error('--directory must be an existing directory')
        paths = [p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()]
    else:
        try:
            paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
        except (OSError, subprocess.CalledProcessError) as error:
            parser.exit(2, f'Cannot inspect Git index: {error}\n')
        paths = [p for p in paths if p]
    blocked = sorted(p for p in paths if restricted(p))
    if blocked:
        print('FAIL: restricted files must not be distributed:')
        print('\n'.join(blocked))
        return 1
    print(f'PASS: {len(paths)} files checked; no restricted paths. Review file contents and third-party rights separately.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
