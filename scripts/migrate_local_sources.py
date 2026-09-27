"""One-time local move; preserve file identity and old-path compatibility."""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone


def inventory(root):
    rows = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(folder) / name
            s = p.lstat()
            rows[str(p.relative_to(root))] = [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, os.readlink(p) if p.is_symlink() else None]
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    old, new = args.source.absolute(), args.destination.absolute()
    assert old.is_dir() and not old.is_symlink(), 'source must be original directory'
    assert not new.exists(), 'destination must not exist'
    new.parent.mkdir(parents=True, exist_ok=True)
    assert old.stat().st_dev == new.parent.stat().st_dev, 'must be same volume'
    before = inventory(old)
    os.rename(old, new)
    try:
        old.symlink_to(os.path.relpath(new, old.parent), target_is_directory=True)
        after = inventory(new)
        assert before == after, 'file identity changed during migration'
        assert old.resolve() == new.resolve()
    except BaseException:
        if old.is_symlink(): old.unlink()
        os.rename(new, old)
        raise
    report = {'date': datetime.now(timezone.utc).isoformat(), 'source': str(old), 'destination': str(new), 'entries': len(before), 'same_device_inode_size_mtime': True, 'compatibility_symlink': os.readlink(old), 'files': before}
    out = new.parents[1] / '.local/migration-inventory.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='files'},ensure_ascii=False))


if __name__ == '__main__': main()
