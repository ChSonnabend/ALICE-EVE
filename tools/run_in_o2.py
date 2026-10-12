#!/usr/bin/env python3
"""Run a command using a loaded Linux O2 shell, without saving its credentials."""
import argparse,os,subprocess
from pathlib import Path


def environment(pid):
    pending=[pid];seen=set()
    while pending:
        current=pending.pop(0)
        if current in seen:continue
        seen.add(current)
        try:
            proc=Path('/proc')/str(current)
            if proc.stat().st_uid!=os.getuid():continue
            env=dict(item.decode().split('=',1) for item in (proc/'environ').read_bytes().split(b'\0') if b'=' in item)
            if env.get('O2_ROOT') and Path(env['O2_ROOT']).is_dir():return env
            pending.extend(int(v) for v in (proc/'task'/str(current)/'children').read_text().split())
        except (OSError,UnicodeError):continue
    raise ValueError('No loaded O2 environment found in that process or its children')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args();command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command:p.error('Provide a command after --')
    return subprocess.run(command,env=environment(a.pid)).returncode

if __name__=='__main__':raise SystemExit(main())
