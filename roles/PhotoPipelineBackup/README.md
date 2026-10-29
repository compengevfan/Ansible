PhotoPipelineBackup
===================

HLT-1, Stage 2. Keeps `\\storage1\Backups\ImmichPhotosAndVideos` in step with
the Immich library at `\\storage3\Immich\library\admin`, **deletions
included**. Only original photos and videos are copied; the Immich database
and config are deliberately out of scope.

It runs on `JAX-WKN001L`, after `PhotoPipelineIngest` in an Ascender workflow,
through `PhotoPipelineBackup.yml`.

**It starts as a dry run.** `photo_backup_dry_run` defaults to `true`; see
*Going live*.

Why it never walks the tree
---------------------------

The library holds hundreds of thousands of files, so a nightly scan of either
side is ruled out. Instead the job asks the Immich API what changed:

- `search/metadata` with `updatedAfter` — new and changed assets
- `search/metadata` with `trashedAfter` — assets moved to the trash

Both searches use `withDeleted: true`, so trashed assets come back too. The
results are merged by asset ID and each asset's `isTrashed` decides the action.

What a run does
---------------

1. Mounts `//storage3.evorigin.com/Immich` read-only and
   `//storage1.evorigin.com/Backups` read-write (read-only during a dry run),
   with credentials written to `/run/photo-backup` for the run only.
2. Checks that every top-level folder in the library also exists in the
   backup root. A wrong path mapping fails here, before anything is copied.
3. Queries Immich for changes since the last successful run, minus
   `photo_backup_overlap_minutes`.
4. For each asset:
   - **live:** copied to the backup unless the backup already has it at the
     same size. A copy goes to `<name>.partial` first and is renamed into
     place, so a half-written file never looks complete.
   - **trashed:** the backup copy is deleted.
5. On success, and only then, records the run's start time as the new
   checkpoint in `/var/lib/photo-pipeline/backup-state.json`.
6. Unmounts both shares, removes the credentials, prunes manifests older than
   `photo_backup_manifest_retention_days`, and pushes the result to Zabbix.

How deletions behave
--------------------

The backup copy is deleted **when the asset goes to the Immich trash**, not
when the trash is emptied. Once Immich empties its trash the asset disappears
from the API entirely, so trashing is the last point at which the job can see
it.

**Restoring from the trash** updates the asset, so the next run copies it
back from Storage3 (the original stays on disk while it is in the trash).

Trash retention is 30 days, far longer than the gap between runs, so normal
deletions are always caught.

### The gap

An asset trashed **and** permanently deleted between two runs (trash emptied
by hand the same day) never appears as trashed, so its backup copy stays.
Nothing is lost by this; the backup just keeps an extra file. A periodic
reconciliation against Immich's full asset list would clean these up; it is
planned with the integrity pass in HLT-1.

Safety checks
-------------

All run before anything is changed:

- **Path mapping:** the backup root must contain every top-level library
  folder (the year folders).
- **Unexpected paths:** an asset whose `originalPath` is outside
  `photo_backup_source_prefix` fails the run rather than being skipped, since
  it means something is not being backed up.
- **Deletion limit:** a run planning more than `photo_backup_max_deletes`
  deletions (default 500) aborts with nothing changed. For a deliberate large
  clean-up in Immich, raise it in the template's extra vars for one run.
- **Containment:** a path that would resolve outside the backup root is
  refused.

A failed run does not advance the checkpoint, so the next run retries the
same window.

The manifest
------------

`/var/lib/photo-pipeline/backup-manifests/<timestamp>.json` (or
`-dryrun.json`). A `summary` block, then one entry per asset: `id`,
`originalPath`, `trashed`, `source`, `destination` and `action` (`copied`,
`replaced`, `present`, `deleted`, `already_absent`, `outside_library`,
`failed`, or `not_run` when a safety check aborted the run).

Credentials
-----------

`PhotoPipelineBackup.yml` runs `GetVaultCreds` with:

| `includecred` | Used for |
|---|---|
| `linuxroot` | SSH to the target |
| `immich` | `HomeLabSecrets/data/immich`: `url` and `api_key` |
| `smbstorage1` | `HomeLabSecrets/data/smb/storage1`: `username`, `password` (optional `domain`) |
| `smbstorage3` | `HomeLabSecrets/data/smb/storage3`: same keys |
| `zabbixapi` | The `history.push` call |

The SMB accounts need read access to the Storage3 `Immich` share and write
(including delete) access to `ImmichPhotosAndVideos` on the Storage1
`Backups` share. The Immich key needs to read assets, trashed ones included.

The SMB credentials are written to a credentials file on tmpfs rather than
passed as mount options, so they never appear in the process list and commas
in a password are safe. The file is removed at the end of every run.

One-time setup
--------------

### Zabbix

On host `JAX-WKN001L.evorigin.com`, as for the ingest job:

1. Item: **Zabbix trapper**, key `photo.backup.status`, type **Text**.
2. Trigger, failed run (High):
   `find(/JAX-WKN001L.evorigin.com/photo.backup.status,,"regexp","^error")=1`
3. Trigger, no run (High), **created disabled** and enabled at go-live:
   `nodata(/JAX-WKN001L.evorigin.com/photo.backup.status,26h)=1`

### Ascender

1. Job template: inventory `Linux`, playbook `PhotoPipelineBackup.yml`, the
   same Vault credential as the ingest job, verbosity 0 or 1, concurrent jobs
   off. No limit needed: the playbook targets `JAX-WKN001L`.
2. Workflow template: the ingest job, then this one on an **Always** edge, so
   trash changes are still mirrored on a night the ingest fails.
3. Move the 03:00 schedule from the ingest job template to the workflow.

Going live
----------

1. Run the template with the default dry run. Check the job output and the
   `-dryrun.json` manifest. The first run starts from the 2026-10-23 seed, so
   expect the three photos ingested that day as `present` plus anything
   ingested since as `copied`.
2. Set `photo_backup_dry_run: false` in the template's extra vars and run it
   once by hand.
3. Build the workflow and move the schedule to it, then enable the no-run
   trigger.

Role Variables
--------------

| Variable | Default | Notes |
|---|---|---|
| `photo_backup_dry_run` | `true` | Storage1 mounted read-only; nothing changed |
| `photo_backup_source_server` / `_share` | `storage3.evorigin.com` / `Immich` | |
| `photo_backup_dest_server` / `_share` | `storage1.evorigin.com` / `Backups` | |
| `photo_backup_source_prefix` | `/usr/src/app/upload/library/admin` | The `originalPath` prefix Immich reports |
| `photo_backup_source_root` | `<storage3 mount>/library/admin` | Where that prefix is on the share |
| `photo_backup_dest_root` | `<storage1 mount>/ImmichPhotosAndVideos` | |
| `photo_backup_initial_checkpoint` | `2026-10-23T00:00:00-04:00` | Used only until the first successful run |
| `photo_backup_overlap_minutes` | `60` | |
| `photo_backup_visibilities` | `[]` | Extra visibilities to search, e.g. `['hidden']` for Live Photo video parts |
| `photo_backup_max_deletes` | `500` | |
| `photo_backup_cifs_opts` | `vers=3.0,iocharset=utf8` | |
| `photo_backup_timeout` | `14400` | Seconds |
| `photo_backup_zabbix_host` | `JAX-WKN001L.evorigin.com` | Exact Zabbix host name |
| `photo_backup_zabbix_item_key` | `photo.backup.status` | |

Known limits
------------

- **Sizes, not hashes.** A backup file is treated as current when its size
  matches. Immich does not edit originals, so this is enough for nightly runs;
  the planned integrity pass is where content would be checked.
- **The gap described above** for assets trashed and purged between runs.
- **Hidden assets.** If Immich's default search leaves out hidden assets
  (Live Photo video parts), set `photo_backup_visibilities: ['hidden']`. Whether
  any arrive depends on what Dropbox uploads for Live Photos; not yet checked.
- **Storage template changes.** If the Immich storage template is changed and
  its migration job moves files, run a one-off full re-sync afterwards.

Dependencies
------------

`GetVaultCreds` (called from the playbook). `community.hashi_vault` and `hvac`
in the execution environment.

License
-------

MIT
