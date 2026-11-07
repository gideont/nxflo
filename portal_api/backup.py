"""Create a consistent SQLite backup without copying a live WAL file."""
import os
from pathlib import Path
import sqlite3
import sys


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        print('No database exists yet; initial deployment needs no backup.')
        return False
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    if temporary.exists() or destination.exists():
        raise ValueError('Backup destination already exists')
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5) as original:
            with sqlite3.connect(temporary) as target:
                original.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup failed integrity verification')
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print('Database backup verified:', destination)
    return True


if __name__ == '__main__':
    backup(os.environ.get('BMS_DATABASE_PATH', '/data/bms_hub.sqlite3'), sys.argv[1])
