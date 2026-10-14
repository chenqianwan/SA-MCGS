"""Run a supplied recovery inspection through this task's SSH control socket."""
from pathlib import Path
import subprocess
import sys

socket = (Path(__file__).resolve().parent / 'ssh_control_path.txt').read_text().strip()
command = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'ConnectTimeout=15', '-o', 'ControlMaster=auto',
           '-o', 'ControlPersist=600', '-S', socket, 'Group3_slogin', 'python3 -']
result = subprocess.run(command, input=sys.stdin.read(), text=True,
                        capture_output=True, timeout=240)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
raise SystemExit(result.returncode)
