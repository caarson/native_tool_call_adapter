#!/usr/bin/env python3
"""Project installer script.

Features:
 - Creates (or reuses) a virtual environment in .venv (override with --venv-dir)
 - Or forcibly recreates it when --fresh is specified
 - Parses dependencies from pyproject.toml ([project].dependencies)
 - Installs them with pip (supports --upgrade)
 - Optionally installs current project in editable mode (--editable)
 - Can emit a requirements.lock style file listing resolved versions (--export)
 - Prints concise status with color (if supported)

Usage examples (PowerShell):
    python installer.py                # create .venv and install deps
    python installer.py --fresh        # delete existing .venv then recreate clean
  python installer.py --upgrade      # upgrade installed packages
  python installer.py --editable     # also pip install -e .
  python installer.py --venv-dir .myenv --export deps.txt
  python installer.py --python C:\\Python313\\python.exe

After successful run:
  Activate venv (PowerShell):  .venv\\Scripts\\Activate.ps1
  Run server:                  uv run main.py  (if uv installed) or python main.py
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import textwrap
import venv
import re
from pathlib import Path
from typing import List

PYPROJECT = Path(__file__).parent / "pyproject.toml"

COLOR = sys.stdout.isatty()

def c(code: str, text: str) -> str:
    if not COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def info(msg: str):
    print(c('36', '[INFO]'), msg)

def warn(msg: str):
    print(c('33', '[WARN]'), msg)

def error(msg: str):
    print(c('31', '[ERROR]'), msg)

def parse_dependencies(pyproject_text: str) -> List[str]:
    # Simple extraction of dependencies = [ ... ] block under [project]
    # This is intentionally lightweight to avoid adding toml dependency.
    m = re.search(r"^dependencies\s*=\s*\[(?P<body>[\s\S]*?)\]", pyproject_text, re.MULTILINE)
    if not m:
        return []
    body = m.group('body')
    deps = []
    for line in body.splitlines():
        line = line.strip().rstrip(',')
        if not line or line.startswith('#'):
            continue
        # Remove wrapping quotes
        if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
            line = line[1:-1]
        if line:
            deps.append(line)
    return deps

def ensure_venv(venv_dir: Path, python_exe: str | None, fresh: bool = False) -> Path:
    if fresh and venv_dir.exists():
        import shutil
        warn(f"--fresh specified: removing existing environment at {venv_dir}")
        shutil.rmtree(venv_dir)
    if venv_dir.exists():
        info(f"Using existing virtual environment: {venv_dir}")
    else:
        info(f"Creating virtual environment at: {venv_dir}")
        builder = venv.EnvBuilder(with_pip=True, upgrade_deps=False)
        builder.create(venv_dir)
    # Determine interpreter path inside venv
    if os.name == 'nt':
        interp = venv_dir / 'Scripts' / 'python.exe'
    else:
        interp = venv_dir / 'bin' / 'python'
    if not interp.exists():
        raise SystemExit("Failed to locate python in virtual environment")
    return interp

def run_pip(python_path: Path, args: List[str]):
    cmd = [str(python_path), '-m', 'pip'] + args
    info('Running: ' + ' '.join(cmd))
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(completed.stdout)
    if completed.returncode != 0:
        raise SystemExit(f"pip command failed with exit code {completed.returncode}")

def export_lock(python_path: Path, out_file: Path):
    # Use pip freeze as a simple lock export
    cmd = [str(python_path), '-m', 'pip', 'freeze']
    info('Exporting resolved dependencies to ' + str(out_file))
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        warn('pip freeze failed; skipping export')
        return
    out_file.write_text(completed.stdout, encoding='utf-8')


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='Install project dependencies into a dedicated virtual environment.')
    parser.add_argument('--venv-dir', default='.venv', help='Virtual environment directory (default: .venv)')
    parser.add_argument('--upgrade', action='store_true', help='Upgrade already installed packages')
    parser.add_argument('--fresh', action='store_true', help='Recreate the virtual environment from scratch (delete if exists)')
    parser.add_argument('--editable', action='store_true', help='Install the project itself in editable mode')
    parser.add_argument('--export', metavar='FILE', help='Export resolved dependency versions (pip freeze) to FILE')
    parser.add_argument('--python', metavar='PYTHON', help='Python interpreter to bootstrap venv (ignored if venv exists)')
    parser.add_argument('--no-color', action='store_true', help='Disable ANSI color output')

    args = parser.parse_args(argv)
    global COLOR
    if args.no_color:
        COLOR = False

    if not PYPROJECT.exists():
        error('pyproject.toml not found; aborting.')
        raise SystemExit(1)

    py_text = PYPROJECT.read_text(encoding='utf-8')
    dependencies = parse_dependencies(py_text)
    if not dependencies:
        warn('No dependencies found in pyproject.toml')

    venv_dir = Path(args.venv_dir)
    venv_python = ensure_venv(venv_dir, args.python, fresh=args.fresh)

    # Upgrade pip first for reliability
    run_pip(venv_python, ['install', '--upgrade', 'pip', 'setuptools', 'wheel'])

    install_cmd = ['install']
    if args.upgrade:
        install_cmd.append('--upgrade')
    install_cmd += dependencies
    if dependencies:
        run_pip(venv_python, install_cmd)

    if args.editable:
        run_pip(venv_python, ['install', '-e', '.'])

    if args.export:
        export_lock(venv_python, Path(args.export))

    info('Installation complete.')
    info(textwrap.dedent(f"""
        Next steps:
          PowerShell: {venv_dir}\\Scripts\\Activate.ps1
          Bash:       source {venv_dir}/bin/activate
          Run:        python main.py --open-gui
    """).strip())

if __name__ == '__main__':
    main()
