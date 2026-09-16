"""snapshot.py — version memory for the brain. Snapshot on every eval run; revert in one command.

Why: iterating on a brain is a hill-climb, and hill-climbs sometimes step DOWN. If an edit makes the agent
worse, you need to (a) SEE that it did (the ledger + brain hash) and (b) get the last-good brain back
instantly (restore). Together with git, this is your permanent record of every version and its score.

    python3 -m eval.lib.snapshot save   <run_id>     # copy brain/*.{yaml,md} → eval/runs/<run_id>/brain/
    python3 -m eval.lib.snapshot list                # list snapshots + their brain hash
    python3 -m eval.lib.snapshot diff   <a> <b>      # unified diff of two snapshots' brains
    python3 -m eval.lib.snapshot restore <run_id>    # copy a snapshot's brain BACK to brain/  (revert)
"""
from __future__ import annotations

import difflib
import shutil
import sys
from pathlib import Path

from agent import config, prompt

RUNS = Path(__file__).resolve().parent.parent / "runs"


def _snap_dir(run_id: str) -> Path:
    return RUNS / run_id / "brain"


def save(run_id: str) -> Path:
    dst = _snap_dir(run_id)
    dst.mkdir(parents=True, exist_ok=True)
    for src in config.BRAIN_FILES:
        shutil.copy2(src, dst / src.name)
    (dst / "BRAIN_HASH").write_text(prompt.brain_hash() + "\n")
    print(f"snapshot saved: {dst}  (brain {prompt.brain_hash()})")
    return dst


def list_snapshots() -> None:
    if not RUNS.exists():
        print("(no runs yet)")
        return
    for run in sorted(p.name for p in RUNS.iterdir() if (p / "brain").is_dir()):
        hp = _snap_dir(run) / "BRAIN_HASH"
        h = hp.read_text().strip() if hp.exists() else "????????????"
        print(f"  {run:<30} brain {h}")


def diff(a: str, b: str) -> None:
    for src in config.BRAIN_FILES:
        fa, fb = _snap_dir(a) / src.name, _snap_dir(b) / src.name
        if not (fa.exists() and fb.exists()):
            continue
        d = difflib.unified_diff(fa.read_text().splitlines(), fb.read_text().splitlines(),
                                 fromfile=f"{a}/{src.name}", tofile=f"{b}/{src.name}", lineterm="")
        out = "\n".join(d)
        if out:
            print(out + "\n")


def restore(run_id: str) -> None:
    src_dir = _snap_dir(run_id)
    if not src_dir.is_dir():
        raise SystemExit(f"no snapshot for run '{run_id}'")
    for src in config.BRAIN_FILES:
        snap = src_dir / src.name
        if snap.exists():
            shutil.copy2(snap, src)
    print(f"brain restored from {run_id} → brain/  (now {prompt.brain_hash()})")
    print("  review `git diff brain/` and commit if this is the version you want to keep.")


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "save":
        save(rest[0])
    elif cmd == "list":
        list_snapshots()
    elif cmd == "diff":
        diff(rest[0], rest[1])
    elif cmd == "restore":
        restore(rest[0])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
