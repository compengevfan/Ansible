#!/usr/bin/env python3
"""File staged Camera Uploads into Photos By Date, inside Dropbox.

Part of the PhotoPipelineIngest role (HLT-1). The playbook has already copied
"Camera Uploads" into a local staging folder and uploaded it to Immich. This
script works out each staged file's capture date, then moves the original
server-side in Dropbox with `rclone moveto`, so nothing is uploaded again.

Capture date, first match wins:
  1. EXIF DateTimeOriginal, CreateDate, MediaCreateDate (exiftool; QuickTime
     times are converted from UTC)
  2. The Camera Uploads file name, which Dropbox sets to the capture time
     ("2026-10-21 18.32.05.jpg")
  3. The file's modification time. Logged as date_source "modtime", since it
     can be the upload time rather than when the photo was taken.

Name collisions in the destination folder are settled by Dropbox content hash:
the same content means the source is a duplicate and is deleted; different
content gets a _1, _2 ... suffix. Dropbox names are case-insensitive, so the
comparison is too.

Writes a JSON manifest of every file and prints a one-line JSON summary as the
last line of stdout. Exits 2 if any file failed, so the playbook fails the run.

rclone reads its remote from RCLONE_CONFIG_* environment variables; no config
file is needed.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

BLOCK_SIZE = 4 * 1024 * 1024
EXIF_TAGS = ("DateTimeOriginal", "CreateDate", "MediaCreateDate")
# "2026-10-21 18.32.05.jpg", "2026-10-21 18.32.05-1.heic", ...
NAME_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2})")


def dropbox_content_hash(path):
    """Dropbox content_hash: SHA-256 over the SHA-256 of each 4 MiB block."""
    overall = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(BLOCK_SIZE), b""):
            overall.update(hashlib.sha256(block).digest())
    return overall.hexdigest()


def plausible(when):
    return when if 1990 <= when.year <= dt.date.today().year + 1 else None


def parse_exif(value):
    # Cameras write "0000:00:00 00:00:00" for unset dates; strptime rejects it.
    if not isinstance(value, str):
        return None
    try:
        return plausible(dt.datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


def read_exif(staging):
    cmd = ["exiftool", "-json", "-quiet", "-quiet", "-m", "-r",
           "-api", "QuickTimeUTC=1", "-d", "%Y-%m-%d %H:%M:%S"]
    cmd += ["-" + tag for tag in EXIF_TAGS]
    cmd.append(staging)
    result = subprocess.run(cmd, capture_output=True, text=True)
    # exiftool exits 1 when some files carry none of the tags; the JSON is
    # still complete. Anything higher is a real failure.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"exiftool exited {result.returncode}: {result.stderr.strip()}")
    if not result.stdout.strip():
        return {}
    return {os.path.realpath(e["SourceFile"]): e for e in json.loads(result.stdout)}


def capture_date(path, name, exif):
    entry = exif.get(os.path.realpath(path), {})
    for tag in EXIF_TAGS:
        when = parse_exif(entry.get(tag))
        if when:
            return when, tag
    match = NAME_DATE.match(name)
    if match:
        try:
            when = plausible(dt.datetime(*map(int, match.groups())))
            if when:
                return when, "filename"
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(os.path.getmtime(path)), "modtime"


def rclone(*args):
    return subprocess.run(["rclone", *args], capture_output=True, text=True)


def mutate(dry_run, *args):
    """Run an rclone command that changes Dropbox, unless this is a dry run."""
    if dry_run:
        return
    result = rclone(*args)
    if result.returncode != 0:
        raise RuntimeError(f"rclone {args[0]} exited {result.returncode}: {result.stderr.strip()[-500:]}")


class DestinationIndex:
    """Lowercased name -> content hash for each destination day folder, listed once."""

    def __init__(self):
        self.folders = {}

    def get(self, remote_dir):
        if remote_dir not in self.folders:
            result = rclone("lsjson", "--files-only", "--hash", "--hash-type", "dropbox", remote_dir)
            if result.returncode == 3:  # directory not found: a new day folder
                entries = []
            elif result.returncode != 0:
                raise RuntimeError(f"rclone lsjson {remote_dir} exited {result.returncode}: {result.stderr.strip()[-500:]}")
            else:
                entries = json.loads(result.stdout)
            self.folders[remote_dir] = {
                e["Name"].lower(): (e.get("Hashes") or {}).get("dropbox") for e in entries
            }
        return self.folders[remote_dir]


def free_name(name, existing):
    stem, ext = os.path.splitext(name)
    n = 1
    while f"{stem}_{n}{ext}".lower() in existing:
        n += 1
    return f"{stem}_{n}{ext}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staging", required=True, help="local copy of the source folder")
    parser.add_argument("--source", required=True, help='e.g. "dropbox:Camera Uploads"')
    parser.add_argument("--dest", required=True, help='e.g. "dropbox:Photos By Date"')
    parser.add_argument("--format", default="%Y/%Y_%m/%Y_%m_%d", help="strftime folder layout")
    parser.add_argument("--manifest", required=True, help="path of the JSON manifest to write")
    parser.add_argument("--dry-run", action="store_true", help="plan only; change nothing in Dropbox")
    args = parser.parse_args()

    started = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    exif = read_exif(args.staging)
    index = DestinationIndex()
    files = []

    for root, dirs, names in os.walk(args.staging):
        dirs.sort()
        for name in sorted(names):
            local = os.path.join(root, name)
            rel = os.path.relpath(local, args.staging).replace(os.sep, "/")
            record = {"source": f"{args.source}/{rel}"}
            try:
                taken, how = capture_date(local, name, exif)
                content_hash = dropbox_content_hash(local)
                dest_dir = f"{args.dest}/{taken.strftime(args.format)}"
                record.update(taken=taken.isoformat(timespec="seconds"),
                              date_source=how, dropbox_hash=content_hash)
                existing = index.get(dest_dir)
                target = name
                if name.lower() in existing:
                    if existing[name.lower()] == content_hash:
                        record.update(action="duplicate_removed", destination=f"{dest_dir}/{name}")
                        mutate(args.dry_run, "deletefile", record["source"])
                        files.append(record)
                        continue
                    target = free_name(name, existing)
                record.update(action="moved", destination=f"{dest_dir}/{target}")
                mutate(args.dry_run, "moveto", record["source"], record["destination"])
                existing[target.lower()] = content_hash
            except Exception as exc:  # one bad file must not stop the rest
                record.update(action="failed", error=str(exc))
            files.append(record)

    counts = {action: sum(1 for f in files if f.get("action") == action)
              for action in ("moved", "duplicate_removed", "failed")}
    summary = {
        "started": started,
        "dry_run": args.dry_run,
        "files": len(files),
        **counts,
        "date_from_filename": sum(1 for f in files if f.get("date_source") == "filename"),
        "date_from_modtime": sum(1 for f in files if f.get("date_source") == "modtime"),
        "manifest": args.manifest,
    }

    tmp = args.manifest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "files": files}, fh, indent=2)
    os.replace(tmp, args.manifest)

    for f in files:
        if f.get("action") == "failed":
            print(f"FAILED {f['source']}: {f['error']}", file=sys.stderr)
    print(json.dumps(summary))
    return 2 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
