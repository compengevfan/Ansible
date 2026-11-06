PhotoPipelineUsb
================

HLT-1, Stage 3. Keeps a detachable USB drive on Storage3 in step with the
Immich library, **deletions included**, so it can be unplugged at any time and
taken to a Windows laptop with every photo and video on it.

It runs on `JAX-WKN001L`, after `PhotoPipelineBackup` in an Ascender workflow,
through `PhotoPipelineUsb.yml`. **On days the drive is unplugged it succeeds
quietly**: no error, no alert.

**It starts as a dry run.** `photo_usb_dry_run` defaults to `true`; see
*Going live*.

How it works
------------

Storage3 is an Asustor appliance (ADM, BusyBox, no Python, no systemd), so
nothing is installed on it. Instead `JAX-WKN001L` drives it over SSH:

- **The drive is found by filesystem UUID** (`blkid`), and its mount point is
  read from `/proc/mounts`. ADM names USB drives `USB1`, `USB2`, … in the order
  it sees them, so the mount point is never assumed.
- **The photos are copied on Storage3 itself**, by `rsync` from
  `/share/Immich/library/admin` to the drive. They never cross the network,
  which matters most for the first full sync of about 1 TB.
- **What to copy and delete comes from the Immich API**, the same delta as
  `PhotoPipelineBackup`, so nothing walks the library or the drive.
- **The checkpoint is kept on the drive**, in `.photo-usb-state.json`. However
  long the drive is away, the next run picks up from that drive's own last
  sync.

### Why not a plain `rsync --delete`

`rsync` alone finds differences by walking both trees, which means listing
about 200,000 files every night, on the drive's side through ADM's NTFS
driver over USB. That is the nightly full scan ruled out for Stage 2. It
would also delete copies when Immich purges an asset (30 days after
trashing) rather than when it is trashed, unlike `PhotoPipelineBackup`. So
Immich supplies the short list, and `rsync` only copies it (`--files-from`).

An occasional full `rsync --delete` would clean up the leftovers described
under *Known limits*; it belongs with the planned reconciliation pass, not
the nightly run.

What a run does
---------------

1. Writes the Storage3 SSH key and host key, from Vault, to `/run/photo-usb`
   (tmpfs) for the run only.
2. Over SSH, looks for the drive by UUID:
   - **not attached:** reports `ok: drive not attached` and stops.
   - **attached but not mounted** (ejected in ADM): reports
     `ok: drive attached but not mounted (ejected)` and stops.
   - **mounted:** carries on.
3. Refuses to write unless `.photo-usb-drive` at the drive's root holds the
   drive's UUID.
4. Reads the drive's checkpoint:
   - **present:** asks Immich for assets changed or trashed since then, minus
     `photo_usb_overlap_minutes` (a *delta* sync).
   - **missing** (new or wiped drive): lists every live asset (a *full* sync).
5. Checks the deletions and sizes the copy with an `rsync --dry-run`. Stops
   with nothing changed if a safety check fails (see below).
6. Copies the live assets the drive is missing (`rsync`, skipping files
   already there at the same size) and deletes the copies of trashed ones.
7. On success, and only then, writes the new checkpoint to the drive.
8. Removes the keys, prunes manifests older than
   `photo_usb_manifest_retention_days`, and pushes the result to Zabbix.

The drive
---------

| | |
|---|---|
| Drive | WD Elements, 1.9 TB, NTFS |
| Filesystem UUID | `682C12C72C128FE4` (`photo_usb_drive_uuid`) |
| Marker | `.photo-usb-drive` at the root, holding the UUID |
| Checkpoint | `.photo-usb-state.json` at the root |
| Photos | `Photos\yyyy\MM\dd\<original file name>`, the Immich library layout |

NTFS because the laptop runs Windows 11; ADM writes it with its own NTFS
driver. The library was 1.0 TB in November 2026. No encryption: ADM cannot
write to a BitLocker volume.

### Using it on the laptop

- **Eject it in ADM before unplugging** (ADM, *External Devices*, Eject). The
  drive is mounted with `force`, so pulling it out mid-write risks a damaged
  NTFS. An ejected drive is reported as such and skipped, not an error.
- **Treat it as read-only on the laptop.** It is a mirror of Immich: a file
  edited there is overwritten if that asset changes in Immich; a file deleted
  there comes back only with a full sync; a file added there stays but is
  unknown to the job. Copy photos off the drive to work on them.
- Plugged back in, it catches up at the next nightly run.

### Replacing or wiping the drive

1. Format the new drive NTFS, plug it in, and note its UUID with `blkid` on
   Storage3.
2. Write the marker: `echo <UUID> > /share/USBn/.photo-usb-drive`.
3. Set `photo_usb_drive_uuid` to the new UUID (role default, or the template's
   extra vars).
4. With no checkpoint on it, the next run is a full sync; see *Going live* for
   the timeout.

To force a full sync on the current drive (say, after a long time away; see
*Known limits*), delete `.photo-usb-state.json` from it.

Safety checks
-------------

All run before anything is changed:

- **Marker:** the drive must carry `.photo-usb-drive` holding its UUID, so no
  other drive is ever written to.
- **Unexpected paths:** an asset whose `originalPath` is outside
  `photo_usb_source_prefix`, or whose relative path contains `..` or control
  characters, fails the run.
- **Deletion limit:** more than `photo_usb_max_deletes` deletions (default 500)
  aborts with nothing changed. Raise it in extra vars for one run after a
  deliberate large clean-up in Immich.
- **Capacity:** if the copy would leave less than `photo_usb_min_free_gb`
  (default 20) free on the drive, nothing is changed.
- **Checkpoint sanity:** a checkpoint with no `Photos` folder next to it, or an
  unreadable one, fails the run rather than quietly starting over.
- **Host key:** SSH uses `StrictHostKeyChecking=yes` against the key in Vault.
  If Storage3's host key changes (firmware reset), the job fails until Vault
  is updated.

A failed run does not advance the checkpoint, so the next run retries the
same window.

The manifest
------------

`/var/lib/photo-pipeline/usb-manifests/<timestamp>.json` (or `-dryrun.json`).
A `summary` block (drive state, mode, counts, bytes, free space), then one
entry per asset: `id`, `originalPath`, `trashed`, `destination`, `source` (for
copies) and `action` (`copied`, `present`, `deleted`, `already_absent`,
`outside_library`, `failed`, `unknown` when rsync failed part way, or
`not_run` when a safety check aborted the run). In a dry run, `copied` and
`deleted` mean "would be".

Credentials
-----------

`PhotoPipelineUsb.yml` runs `GetVaultCreds` with:

| `includecred` | Used for |
|---|---|
| `linuxroot` | SSH to the target |
| `immich` | `HomeLabSecrets/data/immich`: `url` and `api_key` |
| `asustoradmin` | `HomeLabSecrets/data/storage/asustor_admin`: `username`, `ssh_private_key`, `ssh_known_hosts` |
| `zabbixapi` | The `history.push` call |

`ssh_known_hosts` is Storage3's ECDSA host key line, as `ssh-keyscan` prints it
(`storage3.evorigin.com ecdsa-sha2-nistp256 …`). The host name in it must
match `photo_usb_ssh_host`. Storage3 offers no ed25519 host key.

On Storage3, the public key is in `/volume1/home/admin/.ssh/authorized_keys`,
restricted to `JAX-WKN001L`:

    from="192.168.0.104",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA… jax-wkn001l photo-usb to storage3

The `admin` account owns the USB mount (ADM mounts it `uid=999`), so no root
access on Storage3 is needed. Deletions happen on Storage3 directly, so they
bypass the share's `#Recycle` folder.

One-time setup
--------------

Done on 2026-11-06: the SSH key pair and host key stored in Vault, the key
authorised on Storage3, and the marker written to the drive.

### Zabbix

On host `JAX-WKN001L.evorigin.com`, as for the other two jobs:

1. Item: **Zabbix trapper**, key `photo.usb.status`, type **Text**.
2. Trigger, failed run (High):
   `find(/JAX-WKN001L.evorigin.com/photo.usb.status,,"regexp","^error")=1`
3. Trigger, no run (High), **created disabled** and enabled at go-live:
   `nodata(/JAX-WKN001L.evorigin.com/photo.usb.status,26h)=1`

An unplugged drive still reports `ok: drive not attached` every night, so the
no-run trigger only fires when the job itself stops running.

### Ascender

1. Job template: inventory `Linux`, playbook `PhotoPipelineUsb.yml`, the same
   Vault credential as the other two jobs, verbosity 0 or 1, concurrent jobs
   off. No limit needed: the playbook targets `JAX-WKN001L`.
2. Add it to the photo pipeline workflow after the backup job, on an
   **Always** edge.

Going live
----------

1. **Dry run.** Run the template with the default dry run. The first run has
   no checkpoint on the drive, so it is a full sync: expect every live asset
   as `copied` (would be), about 1 TB in `bytes`, and nothing on the drive.
2. **First full sync, by hand, in the daytime.** Set
   `photo_usb_dry_run: false` and `photo_usb_timeout: 86400` in the extra vars
   for this one run (USB 2.0/3.0 speed and ~200,000 files make it a many-hour
   job). If it times out or fails part way, run it again: files already on
   the drive at the same size are skipped.
3. **Go live.** Leave `photo_usb_dry_run: false` in the template's extra vars,
   remove the `photo_usb_timeout` override, add the job to the workflow, and
   enable the no-run trigger.

Role Variables
--------------

| Variable | Default | Notes |
|---|---|---|
| `photo_usb_dry_run` | `true` | Find, plan and size only; nothing written to the drive |
| `photo_usb_ssh_host` | `storage3.evorigin.com` | Must match the host in `ssh_known_hosts` |
| `photo_usb_ssh_user` | `asustoradmin_cred.username` | |
| `photo_usb_drive_uuid` | `682C12C72C128FE4` | Filesystem UUID of the drive |
| `photo_usb_marker_file` | `.photo-usb-drive` | |
| `photo_usb_state_file` | `.photo-usb-state.json` | Checkpoint, on the drive |
| `photo_usb_dest_dir` | `Photos` | Folder on the drive |
| `photo_usb_source_prefix` | `/usr/src/app/upload/library/admin` | The `originalPath` prefix Immich reports |
| `photo_usb_source_root` | `/share/Immich/library/admin` | That prefix on Storage3 |
| `photo_usb_overlap_minutes` | `60` | |
| `photo_usb_visibilities` | `[]` | Keep in step with `photo_backup_visibilities` |
| `photo_usb_max_deletes` | `500` | |
| `photo_usb_min_free_gb` | `20` | |
| `photo_usb_timeout` | `14400` | Seconds; raise for a full sync |
| `photo_usb_zabbix_host` | `JAX-WKN001L.evorigin.com` | Exact Zabbix host name |
| `photo_usb_zabbix_item_key` | `photo.usb.status` | |

Known limits
------------

- **Away longer than the trash retention.** An asset trashed and then purged
  by Immich (30 days) while the drive is away is never seen as trashed, so its
  copy stays on the drive. Nothing is lost; the drive keeps an extra file. The
  planned reconciliation pass would clean these up.
- **Sizes, not hashes**, as in `PhotoPipelineBackup`.
- **Hidden assets** (Live Photo video parts): see `photo_usb_visibilities`.
- **Windows file names.** A file name NTFS cannot hold (for example one with
  `:` or `?`) fails the run, with rsync's error in the job output. Phone
  uploads do not produce these.
- **No "up to date" signal on the drive itself** yet; the checkpoint file's
  `last_success` is the closest thing.

Dependencies
------------

`GetVaultCreds` (called from the playbook). `community.hashi_vault` and `hvac`
in the execution environment. `rsync` on Storage3 (ADM ships 3.4.3).

License
-------

MIT
