#!/usr/bin/env python3
"""Mirror recent Immich changes onto the Storage1 backup copy.

Part of the PhotoPipelineBackup role (HLT-1, Stage 2). Asks the Immich API
which assets changed since the last successful run, then for each one:

  - live asset:    copy the original from the Storage3 library to the backup,
                   unless the backup already has it at the same size
  - trashed asset: delete the backup copy

Restoring an asset from the Immich trash updates it, so the next run copies
it back. Nothing walks the library or the backup tree.

Two searches are made, both with withDeleted so trashed assets are included:
updatedAfter (new and changed assets) and trashedAfter (assets moved to the
trash). Results are merged by asset ID, and isTrashed decides the action.

Safety checks, all before anything is changed:
  - The backup root's top-level folders must match the library's, which
    catches a wrong path mapping before it copies files to the wrong place.
  - Assets whose originalPath is outside the expected library prefix fail
    the run instead of being silently skipped.
  - More than --max-deletes deletions in one run aborts the whole run.
  - A path that would land outside the backup root is refused.

Writes a JSON manifest of every planned action and prints a one-line JSON
summary as the last line of stdout. The checkpoint advances only after a
successful, non-dry run. Exits 2 when anything failed.

The Immich API key is read from the IMMICH_API_KEY environment variable.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

PAGE_SIZE = 1000


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(when):
    return when.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Immich:
    def __init__(self, url, key):
        self.url = url.rstrip("/")
        self.key = key

    def search(self, criteria):
        """Run /api/search/metadata through every page and return the items."""
        items, page = [], 1
        while page:
            body = dict(criteria, size=PAGE_SIZE, page=page)
            req = urllib.request.Request(
                self.url + "/api/search/metadata",
                data=json.dumps(body).encode(),
                headers={"x-api-key": self.key, "Content-Type": "application/json",
                         "Accept": "application/json"},
                method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.load(resp)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:500]
                raise RuntimeError(f"Immich search {criteria} returned HTTP {exc.code}: {detail}") from None
            assets = data.get("assets") or {}
            items.extend(assets.get("items") or [])
            nxt = assets.get("nextPage")
            page = int(nxt) if nxt not in (None, "", 0, "0") else None
        return items


def top_level_dirs(path):
    with os.scandir(path) as it:
        return {e.name for e in it if e.is_dir() and not e.name.startswith(".")}


def read_checkpoint(path, initial):
    try:
        with open(path, encoding="utf-8") as fh:
            return dt.datetime.fromisoformat(json.load(fh)["last_success"].replace("Z", "+00:00"))
    except FileNotFoundError:
        return dt.datetime.fromisoformat(initial.replace("Z", "+00:00"))


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", required=True, help="Immich server URL")
    p.add_argument("--source-prefix", required=True, help="originalPath prefix Immich reports for the library")
    p.add_argument("--source-root", required=True, help="where that prefix is mounted on this host")
    p.add_argument("--dest-root", required=True, help="the backup copy's root")
    p.add_argument("--state", required=True, help="checkpoint file")
    p.add_argument("--initial-checkpoint", required=True, help="ISO time to start from when there is no checkpoint")
    p.add_argument("--overlap-minutes", type=int, default=60)
    p.add_argument("--visibility", action="append", default=[],
                   help="also search this visibility (repeatable); none = Immich's default")
    p.add_argument("--max-deletes", type=int, default=500)
    p.add_argument("--manifest", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    key = os.environ.get("IMMICH_API_KEY")
    if not key:
        sys.exit("IMMICH_API_KEY is not set")
    prefix = a.source_prefix.rstrip("/") + "/"
    dest_root = os.path.realpath(a.dest_root)
    run_started = utcnow()
    checkpoint = read_checkpoint(a.state, a.initial_checkpoint)
    since = iso(checkpoint - dt.timedelta(minutes=a.overlap_minutes))

    summary = {"started": iso(run_started), "dry_run": a.dry_run, "since": since,
               "assets": 0, "copied": 0, "present": 0, "replaced": 0, "deleted": 0,
               "already_absent": 0, "outside_library": 0, "failed": 0, "manifest": a.manifest}
    records = []

    def finish(code, error=None):
        if error:
            summary["error"] = error
        write_json(a.manifest, {"summary": summary, "assets": records})
        for r in records:
            if r["action"] in ("failed", "outside_library"):
                print(f"{r['action'].upper()} {r.get('originalPath')}: {r.get('error', '')}", file=sys.stderr)
        if error:
            print(f"ABORTED: {error}", file=sys.stderr)
        print(json.dumps(summary))
        return code

    # Path mapping check: same top-level (year) folders on both sides.
    src_years, dst_years = top_level_dirs(a.source_root), top_level_dirs(dest_root)
    if not src_years:
        return finish(2, f"no folders under the library mount {a.source_root}")
    missing = sorted(src_years - dst_years)
    if missing:
        return finish(2, f"backup root {dest_root} is missing library folders {missing[:10]}; "
                         "check the path mapping before anything is copied")

    # Ask Immich what changed.
    immich = Immich(a.url, key)
    visibilities = a.visibility or [None]
    found = {}
    try:
        for vis in visibilities:
            extra = {"visibility": vis} if vis else {}
            for crit in ({"updatedAfter": since}, {"trashedAfter": since}):
                for item in immich.search(dict(crit, withDeleted=True, **extra)):
                    found[item["id"]] = item
    except Exception as exc:
        return finish(2, f"could not query Immich: {exc}")
    summary["assets"] = len(found)

    # Plan.
    plan = []
    for item in sorted(found.values(), key=lambda i: i.get("originalPath") or ""):
        path = item.get("originalPath") or ""
        rec = {"id": item["id"], "originalPath": path, "trashed": bool(item.get("isTrashed"))}
        if not path.startswith(prefix):
            rec.update(action="outside_library", error=f"not under {prefix}")
            records.append(rec)
            continue
        rel = path[len(prefix):]
        dest = os.path.realpath(os.path.join(dest_root, rel))
        if not dest.startswith(dest_root + os.sep):
            rec.update(action="failed", error="maps outside the backup root")
            records.append(rec)
            continue
        rec.update(source=os.path.join(a.source_root, rel), destination=dest)
        plan.append(rec)

    deletes = [r for r in plan if r["trashed"] and os.path.lexists(r["destination"])]
    if len(deletes) > a.max_deletes:
        for rec in plan:
            rec["action"] = "not_run"
        records.extend(plan)
        return finish(2, f"{len(deletes)} deletions planned, over the limit of {a.max_deletes}; "
                         "nothing was changed. Raise photo_backup_max_deletes for this run if intended")

    # Apply.
    for rec in plan:
        try:
            if rec["trashed"]:
                if os.path.lexists(rec["destination"]):
                    rec["action"] = "deleted"
                    if not a.dry_run:
                        os.remove(rec["destination"])
                else:
                    rec["action"] = "already_absent"
            else:
                src_size = os.path.getsize(rec["source"])
                if os.path.exists(rec["destination"]):
                    if os.path.getsize(rec["destination"]) == src_size:
                        rec["action"] = "present"
                        records.append(rec)
                        continue
                    rec["action"] = "replaced"
                else:
                    rec["action"] = "copied"
                if not a.dry_run:
                    os.makedirs(os.path.dirname(rec["destination"]), exist_ok=True)
                    partial = rec["destination"] + ".partial"
                    shutil.copy2(rec["source"], partial)
                    os.replace(partial, rec["destination"])
                rec["bytes"] = src_size
        except Exception as exc:  # one bad file must not stop the rest
            rec.update(action="failed", error=str(exc))
        records.append(rec)

    for r in records:
        summary[r["action"]] = summary.get(r["action"], 0) + 1
    ok = summary["failed"] == 0 and summary["outside_library"] == 0
    if ok and not a.dry_run:
        write_json(a.state, {"last_success": iso(run_started)})
    return finish(0 if ok else 2)


if __name__ == "__main__":
    sys.exit(main())
