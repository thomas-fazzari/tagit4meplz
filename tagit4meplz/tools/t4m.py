#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["mutagen==1.48.1"]
# ///
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

from t4mlib.covers import CoverError
from t4mlib.media import read_track
from t4mlib.plan import PlanError, load_plan
from t4mlib.runs import RunNotFoundError, forget_run, list_runs
from t4mlib.scan import collect, scan
from t4mlib.style import StyleError, load_style
from t4mlib.verify import doctor, verify
from t4mlib.write import apply_plan, preview, quarantine, undo

if TYPE_CHECKING:
    from collections.abc import Callable

    from t4mlib.runs import FileRecord, Manifest, RunSummary
    from t4mlib.scan import ScanReport
    from t4mlib.verify import VerifyResult

PLAN_HELP = """plan format:
  {"root": "<dir, default: plan folder>",
   "files": [{"path": "<file relative to root>",
              "paths": ["<several files sharing the same change, instead of path>"],
              "set": {"artist": "X", "genre": ["A", "B"]},
              "remove": ["comment", "raw:<KEY from inspect>"],
              "cover": "<image relative to root>",
              "pictures": "keep | front-only | none"}]}

  set and remove take canonical field names (see t4mlib/fields.py). Lists only for multi-valued fields.
  cover replaces every picture with one JPEG front cover capped by style.toml.
  Paths must exist. No globs."""

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def emit[T](data: T, render: Callable[[T], None] | None) -> None:
    if render:
        render(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def render_scan(data: ScanReport) -> None:
    summary = data["summary"]
    print(f"{summary['files']} files, {summary['albums']} albums")
    for code, count in summary["issues"].items():
        print(f"  {count:4} {code}")
    for item in data["library_issues"]:
        print(f"\n! {item['code']}: {item.get('detail', '')}")
    by_file = {f["path"]: f["issues"] for f in data["files"]}
    for album in data["albums"]:
        covers = ", ".join(f"{k} x{v}" for k, v in album["covers"].items())
        print(f"\n# {album['album'] or '(no album)'} | {album['albumartist']} | {album['label']} | {album['date']}")
        print(f"  {album['count']} tracks, covers: {covers}")
        for item in album["issues"]:
            print(f"  ! {item['code']}: {item.get('detail', '')}")
        for path in album["files"]:
            if by_file.get(path):
                details = "; ".join(i["code"] + (f" ({i['detail']})" if "detail" in i else "") for i in by_file[path])
                print(f"  - {path}: {details}")


def render_verify(results: list[VerifyResult]) -> None:
    bad = [r for r in results if not r["ok"]]
    print(f"{len(results) - len(bad)}/{len(results)} OK")
    for r in bad:
        print(f"BAD {r['path']}: {(r.get('errors') or ['unknown error'])[0]}")


def render_records(records: list[FileRecord]) -> None:
    for record in records:
        print(f"{record['status'].upper():8} {os.path.relpath(record['path'])}")
        if "error" in record:
            print(f"         {record['error']}")
        if "quarantined_to" in record:
            print(f"         -> {record['quarantined_to']}")
        for change in record.get("diff", []):
            print(f"         {change['field']}: {change['before']} -> {change['after']}")


def render_preview(records: list[FileRecord]) -> None:
    print("DRY RUN. Re-run with --apply to write.")
    render_records(records)


def render_manifest(data: Manifest) -> None:
    print(f"run {data['id']} ({data['kind']}). Undo with: t4m.py undo {data['id']}")
    render_records(data["files"])


def render_runs(runs: list[RunSummary]) -> None:
    for run in runs:
        failed = f", {run['failed']} failed" if run["failed"] else ""
        print(f"{run['id']}  {run['kind']:10} {run['files']:4} files{failed}  {run['source']}")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--human", action="store_true", help="readable output instead of JSON")
    common.add_argument("--style", help="style.toml path (default: skill style.toml or $T4M_STYLE)")
    parser = argparse.ArgumentParser(prog="t4m", description="Music library tag audit and repair")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, text: str, epilog: str | None = None) -> argparse.ArgumentParser:
        return sub.add_parser(
            name,
            parents=[common],
            help=text,
            description=text,
            epilog=epilog,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

    p = add("scan", "Inventory a folder and report tag, cover and album issues.")
    p.add_argument("root", type=Path)
    p.add_argument("--no-recursive", action="store_true")
    p.add_argument("--jobs", type=int, default=8)
    p = add("inspect", "Dump every tag, raw key and picture of the given files.")
    p.add_argument("files", type=Path, nargs="+")
    p = add("verify", "Decode files fully and report corruption.")
    p.add_argument("paths", type=Path, nargs="+", help="files or folders")
    p.add_argument("--jobs", type=int, default=8)
    p = add("write", "Apply a JSON plan. Dry run unless --apply.", PLAN_HELP)
    p.add_argument("plan", type=Path)
    p.add_argument("--apply", action="store_true", help="write the files")
    p = add("undo", "Restore the files touched by a run.")
    p.add_argument("run_id")
    p.add_argument("--force", action="store_true", help="restore even if the audio changed since the run")
    p = add("forget", "Delete the snapshot and backups of runs. Only after the user agrees.")
    p.add_argument("run_ids", nargs="+")
    p = add("runs", "List recent runs.")
    p.add_argument("--limit", type=int, default=20)
    p = add("quarantine", "Move files to the quarantine folder of a new run.")
    p.add_argument("files", type=Path, nargs="+")
    p.add_argument("--reason", required=True)
    add("doctor", "Check external binaries.")
    return parser


def status_code(records: list[FileRecord]) -> int:
    return EXIT_OK if all(r["status"] == "ok" for r in records) else EXIT_FAILED


def cmd_doctor(_args: argparse.Namespace) -> int:
    report = doctor()
    emit(report, None)
    return EXIT_OK if all(report.values()) else EXIT_FAILED


def cmd_inspect(args: argparse.Namespace) -> int:
    emit([asdict(read_track(f)) for f in args.files], None)
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    results = verify([f for p in args.paths for f in collect(p)], args.jobs)
    emit(results, render_verify if args.human else None)
    return EXIT_OK if all(r["ok"] for r in results) else EXIT_FAILED


def cmd_runs(args: argparse.Namespace) -> int:
    emit(list_runs(args.limit), render_runs if args.human else None)
    return EXIT_OK


def cmd_forget(args: argparse.Namespace) -> int:
    emit([str(forget_run(run_id)) for run_id in args.run_ids], None)
    return EXIT_OK


def cmd_quarantine(args: argparse.Namespace) -> int:
    manifest = quarantine([f.resolve() for f in args.files], args.reason)
    emit(manifest, render_manifest if args.human else None)
    return status_code(manifest["files"])


def cmd_scan(args: argparse.Namespace) -> int:
    report = scan(args.root, load_style(args.style), recursive=not args.no_recursive, jobs=args.jobs)
    emit(report, render_scan if args.human else None)
    return EXIT_OK


def cmd_write(args: argparse.Namespace) -> int:
    style = load_style(args.style)
    changes = load_plan(args.plan)
    if not args.apply:
        emit(preview(changes, style), render_preview if args.human else None)
        return EXIT_OK
    manifest = apply_plan(changes, style, str(args.plan.resolve()))
    emit(manifest, render_manifest if args.human else None)
    return status_code(manifest["files"])


def cmd_undo(args: argparse.Namespace) -> int:
    manifest = undo(args.run_id, load_style(args.style), force=args.force)
    emit(manifest, render_manifest if args.human else None)
    return status_code(manifest["files"])


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "doctor": cmd_doctor,
    "inspect": cmd_inspect,
    "verify": cmd_verify,
    "runs": cmd_runs,
    "forget": cmd_forget,
    "quarantine": cmd_quarantine,
    "scan": cmd_scan,
    "write": cmd_write,
    "undo": cmd_undo,
}


def main() -> int:
    args = build_parser().parse_args()
    try:
        return COMMANDS[args.command](args)
    except (PlanError, StyleError, CoverError, RunNotFoundError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
