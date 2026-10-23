PhotoPipelineIngest
===================

HLT-1, Stage 1. Takes new photos and videos from Dropbox's `Camera Uploads`,
uploads them to Immich, then files the originals into `Photos By Date` inside
Dropbox. It replaces `PictureOrg.bat` and `PhotoOrganizer.ps1` on `JAX-WKN101`,
and needs no Dropbox client: rclone talks to the Dropbox API directly.

It runs on `JAX-WKN001L` (the host's name in the Ascender `Linux` inventory),
scheduled from Ascender through
`PhotoPipelineIngest.yml`.

**It starts as a dry run.** `photo_dry_run` defaults to `true`; see *Going live*.

What a run does
---------------

1. Installs or confirms the tools: `rclone` and `perl-Image-ExifTool` from EPEL,
   and `immich-go` at the pinned `immich_go_version` under
   `/opt/immich-go/<version>`, linked to `/usr/local/bin/immich-go`.
2. Empties `/var/lib/photo-pipeline/staging`, then `rclone copy`s
   `dropbox:Camera Uploads` into it. The Dropbox API only lists files that have
   finished uploading, so a half-synced file cannot be picked up.
3. Uploads the staging folder with `immich-go upload from-folder`. immich-go
   skips anything Immich already has (checksum match).
4. **If the upload fails, the run stops here.** Nothing leaves `Camera Uploads`,
   and the next run tries again.
5. `photo_organize.py` dates each file and moves the original server-side with
   `rclone moveto` to `Photos By Date/yyyy/yyyy_MM/yyyy_MM_dd/`. No re-upload.
6. Writes a JSON manifest, empties staging, prunes manifests older than
   `photo_manifest_retention_days`, and pushes the result to Zabbix.

A failure anywhere in steps 2 to 5 is caught, reported to Zabbix as `error`, and
re-raised, so the Ascender job shows as failed.

How files are dated
-------------------

First match wins:

1. EXIF `DateTimeOriginal`, `CreateDate`, `MediaCreateDate`, read with
   exiftool. QuickTime (video) times are converted from UTC.
2. The file name. Dropbox names Camera Uploads files after the capture time,
   e.g. `2026-10-21 18.32.05.jpg`.
3. The file's modification time. This one can be the upload time rather than
   when the photo was taken, so it is counted (`date_from_modtime`) and marked
   `"date_source": "modtime"` in the manifest.

Dates outside 1990 to next year are treated as unset, which catches cameras
that write `0000:00:00`.

Name collisions
---------------

When the destination day folder already has a file of that name (compared
case-insensitively, as Dropbox does), the two are compared by Dropbox content
hash:

- **Same content:** the source is a re-upload. It is deleted from
  `Camera Uploads`; the copy already in `Photos By Date` stays.
- **Different content:** the source is moved in as `name_1`, `name_2`, and so on.

The manifest
------------

`/var/lib/photo-pipeline/manifests/<timestamp>.json` (or `-dryrun.json`) on the
target. A `summary` block, then one entry per file: `source`, `destination`,
`action` (`moved`, `duplicate_removed`, `failed`), `taken`, `date_source` and
`dropbox_hash`.

For Stage 2: the manifest records Dropbox paths, not where Immich stored the
file. Immich renames files into its own library layout, so Stage 2 still has to
map each entry to an Immich asset, by content hash or through the Immich API.

Credentials
-----------

`PhotoPipelineIngest.yml` runs `GetVaultCreds` with:

| `includecred` | Used for |
|---|---|
| `linuxroot` | SSH to the target, as in `ConfigureLinux.yml` |
| `immich` | `HomeLabSecrets/data/immich`: `api_key`, and `url` for the Immich server |
| `dropbox` | `HomeLabSecrets/data/dropbox`: `app_key`, `app_secret`, `token` for the Dropbox app |
| `zabbixapi` | The `history.push` call |

The Dropbox values reach rclone as `RCLONE_CONFIG_DROPBOX_*` environment
variables on the tasks that call it. No `rclone.conf` is written and nothing
secret is left on the host. The `token` may be stored in Vault as a JSON
string or as an object.

The Immich API key goes on the immich-go command line, so that task is
`no_log`. Its output is shown by the task after it.

Don't run the job above verbosity 2: at higher levels Ansible can echo task
environments, which would include the Dropbox token.

One-time setup
--------------

### Zabbix

On host `JAX-WKN001L.evorigin.com` (Zabbix matches host names exactly, case
included, so the item, triggers and `photo_zabbix_host` must all use this spelling):

1. Item: type **Zabbix trapper**, key `photo.pipeline.status`, type of
   information **Text**.
2. Trigger, failed run (High):
   `find(/JAX-WKN001L.evorigin.com/photo.pipeline.status,,"regexp","^error")=1`
3. Trigger, no run (High), which also covers Ascender or the host being down:
   `nodata(/JAX-WKN001L.evorigin.com/photo.pipeline.status,26h)=1`

The `zabbixapi` token's user needs write access to that host.

Values look like `ok: 14 files: 13 moved, 1 duplicates removed, 0 dated by
modification time`, `ok: nothing in Camera Uploads`, or `error: <failed step>`.

### Ascender

1. Use the `Linux` inventory, where the host is `JAX-WKN001L`. The playbook
   targets that name by default, and Ansible matches it exactly, case included:
   a mismatch skips every play and the job still reports success.
2. Job template: playbook `PhotoPipelineIngest.yml`, the same Vault credential
   as the other `GetVaultCreds` jobs, verbosity 0 or 1, concurrent jobs off.
3. Schedule: daily at 03:00 (America/New_York), the slot `PictureOrg.bat` used.

Going live
----------

1. Run the template with the default dry run. Check the job output and the
   `-dryrun.json` manifest: the planned destinations, how many files fall back to
   `modtime`, and any `failed` entries.
2. **Disable the Windows scheduled task on `JAX-WKN101`.** Both jobs move files
   out of `Camera Uploads`, so they must never both be active.
3. Set `photo_dry_run: false` in the template's extra vars and enable the
   schedule.

Role Variables
--------------

| Variable | Default | Notes |
|---|---|---|
| `photo_dry_run` | `true` | immich-go `--dry-run`, and no Dropbox changes |
| `photo_source_dir` | `Camera Uploads` | Relative to the Dropbox root |
| `photo_dest_dir` | `Photos By Date` | Relative to the Dropbox root |
| `photo_dest_format` | `%Y/%Y_%m/%Y_%m_%d` | strftime layout under `photo_dest_dir` |
| `photo_base_dir` | `/var/lib/photo-pipeline` | Staging and manifests live under it |
| `photo_manifest_retention_days` | `90` | |
| `photo_rclone_extra_args` | `[]` | Download flags, e.g. `['--bwlimit', '20M']` if the Gitea runner on the same host slows down |
| `immich_server_url` | `immich_cred.url` | From Vault; set it in extra vars only to override for a test |
| `immich_go_version` | `0.32.0` | Check the upload flags in `tasks/main.yml` against the release notes before bumping |
| `immich_go_upload_timeout` | `14400` | Seconds; the upload runs async so long uploads don't hit SSH timeouts |
| `photo_zabbix_report` | `true` | Dry runs never report |
| `photo_zabbix_host` | `JAX-WKN001L.evorigin.com` | Exact Zabbix host name, case included |
| `photo_zabbix_item_key` | `photo.pipeline.status` | |

Known limits
------------

- **immich-go's exit code is the only upload check.** If it exits 0 while
  rejecting individual files, those files are still filed into
  `Photos By Date`. Its output is in the job log.
- **Every file is moved**, not just photos and videos, the same as
  `PhotoOrganizer.ps1`. Files exiftool can't read are dated by name or
  modification time.
- **Duplicates are only detected by same name and content.** Identical content
  under a different name is moved in as a second file.
- **A failure before the run block** (installing tools) fails the job without a
  Zabbix push. The `nodata` trigger catches it if it persists.

Dependencies
------------

`GetVaultCreds` (called from the playbook). `community.hashi_vault` and `hvac`
in the execution environment. EPEL and GitHub reachable from the target.

License
-------

MIT
