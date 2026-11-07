#!/usr/bin/env python3
"""Keep the detachable USB photo drive on Storage3 in step with Immich.

Part of the PhotoPipelineUsb role (HLT-1, Stage 3). Runs on JAX-WKN001L and
drives Storage3 over SSH, so the photos are copied disk to disk on Storage3
and never cross the network:

  1. Find the drive by filesystem UUID (blkid) and its mount point
     (/proc/mounts). Not attached, or attached but not mounted (ejected):
     report that and exit 0, so an unplugged day raises no alert.
  2. Refuse to write unless the marker file at the drive's root holds the
     drive's UUID.
  3. Read the checkpoint from the state file on the drive. With a checkpoint,
     ask Immich which assets changed or were trashed since then (minus the
     overlap). Without one (new or wiped drive), list every live asset.
  4. Trashed assets: delete their copies on the drive. Live assets: rsync
     them from the library onto the drive, on Storage3, skipping files
     already there at the same size.
  5. On success, and only then, write the new checkpoint to the drive.

The checkpoint lives on the drive rather than on this host, so however long
the drive is away, the next run picks up from its own last sync.

Safety checks, all before anything is changed:
  - The marker file must be present and match the UUID.
  - Assets whose originalPath is outside the expected library prefix, or
    whose relative path is unsafe (.., control characters), fail the run.
    The exception is --skip-prefix: files Immich generated itself (the
    videos it extracts from Android motion photos), which are skipped.
  - More than --max-deletes deletions in one run aborts the whole run.
  - An rsync dry run sizes the copy first; if it would leave less than
    --min-free-gb free on the drive, nothing is changed.

Writes a JSON manifest of every planned action and prints a one-line JSON
summary as the last line of stdout. Exits 2 when anything failed.

The Immich API key is read from the IMMICH_API_KEY environment variable.
"""
import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request

PAGE_SIZE = 1000
SHORT_TIMEOUT = 300

# Remote helpers. Storage3 runs BusyBox (no Python, no awk assumed), so these
# stick to POSIX sh, grep, cut, head, tail, tr and df.

# Args: uuid, marker file name, destination folder name.
PROBE_SH = r'''
uuid=$1; marker=$2; destdir=$3
dev=$(blkid 2>/dev/null | grep -F " UUID=\"$uuid\"" | head -n 1 | cut -d: -f1)
if [ -z "$dev" ]; then echo state=absent; exit 0; fi
echo "device=$dev"
mp=$(grep "^$dev " /proc/mounts | head -n 1 | cut -d" " -f2)
if [ -z "$mp" ]; then echo state=unmounted; exit 0; fi
echo "mount=$mp"
if [ -f "$mp/$marker" ]; then
  echo "marker=$(head -n 1 "$mp/$marker" | tr -d "\r\n ")"
else
  echo marker=
fi
if [ -d "$mp/$destdir" ]; then echo dest_exists=1; else echo dest_exists=0; fi
set -- $(df -P -k "$mp" | tail -n 1)
echo "avail_kb=$4"
echo state=mounted
'''

# Args: file. Prints the file if it exists.
READ_SH = r'''if [ -f "$1" ]; then cat "$1"; fi'''

# Args: file. Writes stdin to the file via a temporary file.
WRITE_SH = r'''cat > "$1.tmp" && mv -f "$1.tmp" "$1"'''

# Args: check|apply. Reads absolute paths, one per line, from stdin.
DELETE_SH = r'''
mode=$1
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if [ -e "$f" ] || [ -L "$f" ]; then
    if [ "$mode" = apply ]; then
      if rm -f -- "$f"; then printf 'deleted\t%s\n' "$f"; else printf 'failed\t%s\n' "$f"; fi
    else
      printf 'deleted\t%s\n' "$f"
    fi
  else
    printf 'already_absent\t%s\n' "$f"
  fi
done
'''


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(when):
    return when.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


class RemoteError(RuntimeError):
    pass


class Remote:
    """Runs commands on Storage3 over SSH with a pinned host key."""

    def __init__(self, target, key, known_hosts):
        self.base = [
            "ssh", "-F", "/dev/null", "-i", key,
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=10",
            "-o", "LogLevel=ERROR", target,
        ]

    def run(self, argv, stdin=b"", timeout=SHORT_TIMEOUT):
        """Run argv remotely. Returns (rc, stdout, stderr); raises on SSH failure."""
        cmd = " ".join(shlex.quote(a) for a in argv)
        try:
            p = subprocess.run(self.base + [cmd], input=stdin, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RemoteError(f"timed out after {timeout}s: {argv[0]}") from None
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        if p.returncode == 255:
            raise RemoteError(f"ssh failed: {err.strip()[-500:]}")
        return p.returncode, out, err

    def sh(self, script, *args, stdin=b"", timeout=SHORT_TIMEOUT):
        return self.run(["sh", "-c", script, "sh"] + list(args), stdin=stdin, timeout=timeout)


class Immich:
    def __init__(self, url, key):
        self.url = url.rstrip("/")
        self.key = key

    def search(self, criteria):
        """Run /api/search/metadata through every page; keep only the fields used."""
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
            for i in assets.get("items") or []:
                items.append({"id": i["id"], "originalPath": i.get("originalPath") or "",
                              "isTrashed": bool(i.get("isTrashed"))})
            nxt = assets.get("nextPage")
            page = int(nxt) if nxt not in (None, "", 0, "0") else None
        return items


def safe_rel(rel):
    if not rel or rel.startswith("/") or any(c in rel for c in "\0\n\r"):
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def parse_kv(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def stat_number(stats, label):
    m = re.search(re.escape(label) + r":\s*([\d,.]+)", stats)
    return int(re.sub(r"\D", "", m.group(1))) if m else 0


def rsync(remote, source_root, dest_root, rels, dry_run, timeout):
    """rsync the listed files on Storage3. Returns (rc, copied rels, bytes, stderr)."""
    # -8 prints UTF-8 file names as they are instead of escaping them, so the
    # COPIED lines match the names sent. No -p/-o/-g: the drive is NTFS.
    argv = ["rsync", "-t", "-8", "--size-only", "--omit-dir-times", "--from0", "--files-from=-",
            "--no-human-readable", "--stats", "--out-format=COPIED:%n"]
    if dry_run:
        argv.append("--dry-run")
    argv += [source_root.rstrip("/") + "/", dest_root.rstrip("/") + "/"]
    data = b"".join(r.encode("utf-8") + b"\0" for r in rels)
    rc, out, err = remote.run(argv, stdin=data, timeout=timeout)
    copied = [line[len("COPIED:"):] for line in out.splitlines()
              if line.startswith("COPIED:") and not line.endswith("/")]
    return rc, copied, stat_number(out, "Total transferred file size"), err


def delete(remote, paths, mode):
    """Check or delete the listed absolute paths. Returns {path: action}."""
    if not paths:
        return {}
    data = "".join(p + "\n" for p in paths).encode("utf-8")
    rc, out, err = remote.sh(DELETE_SH, mode, stdin=data)
    results = {}
    for line in out.splitlines():
        action, _, path = line.partition("\t")
        results[path] = action
    if rc != 0 or len(results) != len(paths):
        raise RemoteError(f"delete {mode} returned {rc} with {len(results)}/{len(paths)} results: {err.strip()[-300:]}")
    return results


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", required=True, help="Immich server URL")
    p.add_argument("--ssh-target", required=True, help="user@host for Storage3")
    p.add_argument("--ssh-key", required=True, help="private key file")
    p.add_argument("--known-hosts", required=True, help="known_hosts file holding Storage3's host key")
    p.add_argument("--drive-uuid", required=True, help="filesystem UUID of the USB drive")
    p.add_argument("--marker", required=True, help="marker file name at the drive's root")
    p.add_argument("--state-name", required=True, help="checkpoint file name at the drive's root")
    p.add_argument("--dest-dir", required=True, help="folder on the drive that holds the photos")
    p.add_argument("--source-prefix", required=True, help="originalPath prefix Immich reports for the library")
    p.add_argument("--source-root", required=True, help="where that prefix is on Storage3")
    p.add_argument("--skip-prefix", action="append", default=[],
                   help="originalPath prefix of files Immich generated itself, skipped (repeatable)")
    p.add_argument("--overlap-minutes", type=int, default=60)
    p.add_argument("--visibility", action="append", default=[],
                   help="also search this visibility (repeatable); none = Immich's default")
    p.add_argument("--max-deletes", type=int, default=500)
    p.add_argument("--min-free-gb", type=float, default=20)
    p.add_argument("--rsync-timeout", type=int, default=14000)
    p.add_argument("--manifest", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    key = os.environ.get("IMMICH_API_KEY")
    if not key:
        sys.exit("IMMICH_API_KEY is not set")
    prefix = a.source_prefix.rstrip("/") + "/"
    skip_prefixes = [s.rstrip("/") + "/" for s in a.skip_prefix]
    run_started = utcnow()
    remote = Remote(a.ssh_target, a.ssh_key, a.known_hosts)

    summary = {"started": iso(run_started), "dry_run": a.dry_run, "drive": "unknown",
               "mode": None, "since": None, "assets": 0, "copied": 0, "bytes": 0, "present": 0,
               "deleted": 0, "already_absent": 0, "outside_library": 0, "failed": 0,
               "free_gb": None, "manifest": a.manifest}
    records = []

    count_keys = ("copied", "present", "deleted", "already_absent", "skipped_derived",
                  "outside_library", "failed")

    def finish(code, error=None):
        # Count from the records on every exit, aborts included.
        for k in count_keys:
            summary[k] = 0
        for r in records:
            summary[r["action"]] = summary.get(r["action"], 0) + 1
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

    # 1. Is the drive here?
    try:
        rc, out, err = remote.sh(PROBE_SH, a.drive_uuid, a.marker, a.dest_dir)
    except RemoteError as exc:
        return finish(2, f"could not reach Storage3: {exc}")
    probe = parse_kv(out)
    summary["drive"] = probe.get("state", "unknown")
    if rc != 0 or summary["drive"] not in ("absent", "unmounted", "mounted"):
        return finish(2, f"drive check on Storage3 failed (rc {rc}): {err.strip()[-300:] or out.strip()[-300:]}")
    if summary["drive"] != "mounted":
        return finish(0)
    mount = probe["mount"]
    summary["mount"] = mount
    try:
        avail = int(probe.get("avail_kb", "")) * 1024
    except ValueError:
        return finish(2, f"could not read free space on {mount}")
    summary["free_gb"] = round(avail / 1e9, 1)

    # 2. Is it the photo drive?
    if probe.get("marker") != a.drive_uuid:
        return finish(2, f"drive {a.drive_uuid} is mounted at {mount} but {a.marker} is missing "
                         "or does not hold its UUID; refusing to write to it")
    dest_root = f"{mount}/{a.dest_dir}"
    state_path = f"{mount}/{a.state_name}"

    # 3. Where did the drive's last sync stop?
    try:
        rc, out, err = remote.sh(READ_SH, state_path)
    except RemoteError as exc:
        return finish(2, f"could not read {state_path}: {exc}")
    checkpoint = None
    if out.strip():
        try:
            checkpoint = parse_iso(json.loads(out)["last_success"])
        except (ValueError, KeyError, TypeError) as exc:
            return finish(2, f"{state_path} is unreadable ({exc}); fix or delete it for a full sync")
        if probe.get("dest_exists") != "1":
            return finish(2, f"{state_path} exists but {dest_root} does not; delete the state file "
                             "for a full sync if the photos were removed on purpose")

    immich = Immich(a.url, key)
    visibilities = a.visibility or [None]
    found = {}
    try:
        for vis in visibilities:
            extra = {"visibility": vis} if vis else {}
            if checkpoint:
                since = iso(checkpoint - dt.timedelta(minutes=a.overlap_minutes))
                summary.update(mode="delta", since=since)
                searches = [{"updatedAfter": since, "withDeleted": True},
                            {"trashedAfter": since, "withDeleted": True}]
            else:
                summary.update(mode="full", since=None)
                searches = [{}]
            for crit in searches:
                for item in immich.search(dict(crit, **extra)):
                    found[item["id"]] = item
    except Exception as exc:
        return finish(2, f"could not query Immich: {exc}")
    summary["assets"] = len(found)

    # 4. Plan.
    copies, trashed = {}, {}
    for item in sorted(found.values(), key=lambda i: i["originalPath"]):
        path = item["originalPath"]
        rec = {"id": item["id"], "originalPath": path, "trashed": item["isTrashed"]}
        if any(path.startswith(s) for s in skip_prefixes):
            # e.g. the video Immich extracts from an Android motion photo; the
            # original photo in the library still holds it.
            rec["action"] = "skipped_derived"
            records.append(rec)
            continue
        if not path.startswith(prefix):
            rec.update(action="outside_library", error=f"not under {prefix}")
            records.append(rec)
            continue
        rel = path[len(prefix):]
        if not safe_rel(rel):
            rec.update(action="failed", error="unsafe relative path")
            records.append(rec)
            continue
        rec["destination"] = f"{dest_root}/{rel}"
        if rec["trashed"]:
            if checkpoint:  # a full sync only copies; there is nothing on the drive to delete
                trashed[rec["destination"]] = rec
        else:
            rec["source"] = f"{a.source_root.rstrip('/')}/{rel}"
            copies[rel] = rec
    if any(r["action"] in ("failed", "outside_library") for r in records):
        for rec in list(copies.values()) + list(trashed.values()):
            rec["action"] = "not_run"
            records.append(rec)
        return finish(2, "some assets could not be mapped onto the drive; nothing was changed")

    try:
        checked = delete(remote, list(trashed), "check")
    except RemoteError as exc:
        return finish(2, f"could not check deletions: {exc}")
    to_delete = [p for p, act in checked.items() if act == "deleted"]
    if len(to_delete) > a.max_deletes:
        for rec in list(copies.values()) + list(trashed.values()):
            rec["action"] = "not_run"
            records.append(rec)
        return finish(2, f"{len(to_delete)} deletions planned, over the limit of {a.max_deletes}; "
                         "nothing was changed. Raise photo_usb_max_deletes for this run if intended")

    # Size the copy before writing anything.
    would_copy, need = [], 0
    if copies:
        try:
            rc, would_copy, need, err = rsync(remote, a.source_root, dest_root, list(copies), True,
                                              a.rsync_timeout)
        except RemoteError as exc:
            return finish(2, f"rsync dry run failed: {exc}")
        if rc != 0:
            return finish(2, f"rsync dry run exited {rc}: {err.strip()[-500:]}")
    reserve = int(a.min_free_gb * 1e9)
    if need > avail - reserve:
        for rec in list(copies.values()) + list(trashed.values()):
            rec["action"] = "not_run"
            records.append(rec)
        return finish(2, f"copy needs {need / 1e9:.1f} GB but the drive has {avail / 1e9:.1f} GB free "
                         f"and {a.min_free_gb:g} GB is kept in reserve; nothing was changed")

    errors = []
    if a.dry_run:
        copied, nbytes, deleted = set(would_copy), need, checked
    else:
        copied, nbytes = set(), 0
        if copies:
            try:
                rc, done, nbytes, err = rsync(remote, a.source_root, dest_root, list(copies), False,
                                              a.rsync_timeout)
                copied = set(done)
                if rc != 0:
                    errors.append(f"rsync exited {rc}: {err.strip()[-500:]}")
            except RemoteError as exc:
                errors.append(f"rsync failed: {exc}")
        try:
            deleted = delete(remote, list(trashed), "apply")
        except RemoteError as exc:
            errors.append(f"deletions failed: {exc}")
            deleted = {}

    for rel, rec in copies.items():
        if rel in copied:
            rec["action"] = "copied"
        elif errors and not a.dry_run:
            rec["action"] = "unknown"  # rsync failed part way; the next run retries
        else:
            rec["action"] = "present"
        records.append(rec)
    for dest, rec in trashed.items():
        rec["action"] = deleted.get(dest, "unknown")
        records.append(rec)

    summary["bytes"] = nbytes
    summary["free_gb"] = round((avail - (0 if a.dry_run else nbytes)) / 1e9, 1)

    ok = not errors and not any(r["action"] in ("failed", "unknown") for r in records)
    if ok and not a.dry_run:
        state = json.dumps({"last_success": iso(run_started), "drive_uuid": a.drive_uuid,
                            "written_by": "PhotoPipelineUsb (HLT-1)"}, indent=2) + "\n"
        try:
            rc, out, err = remote.sh(WRITE_SH, state_path, stdin=state.encode())
            if rc != 0:
                return finish(2, f"could not write {state_path} (rc {rc}): {err.strip()[-300:]}")
        except RemoteError as exc:
            return finish(2, f"could not write {state_path}: {exc}")
    return finish(0 if ok else 2, "; ".join(errors) or None)


if __name__ == "__main__":
    sys.exit(main())
