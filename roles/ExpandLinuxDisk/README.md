ExpandLinuxDisk
===============

Grows a Linux filesystem into space that has already been added to the virtual
disk. It is the in-guest half of a disk expansion only — **grow the disk in
Proxmox or vSphere first**, then run this.

The chain it runs is the manual one:

    rescan  ->  growpart  ->  pvresize  ->  lvextend  ->  xfs_growfs / resize2fs

Every step is a no-op when there is nothing left to grow, so the role is safe to
re-run and safe to run against a host whose disk was never expanded — it just
reports the size and does nothing.

Nothing is unmounted and nothing reboots. On XFS the grow is online, which is
why the template's layout can be expanded while the server is in service.

What it does
------------

1. Fails early if `growpart` is missing, pointing at `cloud-utils-growpart`.
2. Works out what is under `expand_disk_mount` (default `/`): the filesystem
   device and type, whether LVM is in the chain, and from there the volume
   group, the physical volume, the partition and the disk.
3. Writes `1` to `/sys/class/block/<disk>/device/rescan` so a disk grown while
   the VM was running is seen without a reboot.
4. `growpart /dev/<disk> <n>` to grow the partition into the new space.
5. `pvresize`, then `lvextend -l +100%FREE`, when the filesystem is on an LV.
6. `xfs_growfs <mount>` for XFS, `resize2fs <device>` for ext2/3/4.
7. Prints the before and after size of the filesystem.

Discovery, not hard-coded devices
---------------------------------

The AlmaLinux template's chain is `/dev/sda2` → PV → `almalinux` VG →
`/dev/almalinux/root` → `/`, and hard-coding that would have been shorter. It is
discovered instead because `sda` is only right for a SCSI controller: a Proxmox
VM on virtio-blk is `/dev/vda2`, and NVMe is `/dev/nvme0n1p2` with a partition
number that cannot be read off the end of the name. The partition number comes
from `/sys/class/block/<part>/partition` for that reason.

The same discovery is what makes the role work on a non-LVM host, or on a data
disk, without a second code path — `pvresize` and `lvextend` are simply skipped
when the filesystem sits straight on a partition.

Requirements
------------

- `cloud-utils-growpart` on the target. `ConfigureLinux` installs it as part of
  the baseline; hosts built before that need `dnf install cloud-utils-growpart`
  once, or a run of `ConfigureLinux.yml`.
- `lvm2` and the filesystem tool (`xfsprogs` or `e2fsprogs`) — both are on an
  AlmaLinux 9 base install.
- SSH as root, or an account that can act as root. Like `ConfigureLinux`, the
  tasks do not use `become`; `ExpandLinuxDisk.yml` connects with the `linuxroot`
  credential from Vault.
- Only one filesystem is grown per run. Run it again with a different
  `expand_disk_mount` for a second one.

Role Variables
--------------

See `defaults/main.yml`.

| Variable | Default | Notes |
|---|---|---|
| `expand_disk_mount` | `/` | The filesystem to grow. Everything else is discovered from it |
| `expand_disk_partition` | `""` | Override the partition to grow, full path e.g. `/dev/sdb1` |
| `expand_disk_rescan` | `true` | Rescan the disk first. Ignored where there is no rescan node |

`expand_disk_partition` only has to be set when a volume group spans more than
one physical volume, which is when the role cannot know which disk grew. It
fails with that message rather than guessing.

Idempotency
-----------

Two of the commands exit non-zero for the "already done" case, and both are
treated as unchanged rather than failed:

- `growpart` exits 1 with `NOCHANGE: partition N is size ...` when the partition
  already fills the disk.
- `lvextend -l +100%FREE` exits non-zero with `matches existing size` when the
  volume group has no free extents.

`pvresize` reports success either way and cannot be read for this, so the
physical volume size is measured before and after and the *check* task carries
the changed status.

Check mode
----------

`--check` is useful as a dry run: every discovery task carries
`check_mode: false` so it still reports the device chain it would act on, and
the five commands that change something are skipped.

Dependencies
------------

None. `ExpandLinuxDisk.yml` pairs it with `GetVaultCreds` (`linuxroot`).

Example Playbook
----------------

`ExpandLinuxDisk.yml` in the repository root. It defaults to the `AlmaLinux`
group, so in practice give it a host:

    ansible-playbook ExpandLinuxDisk.yml -e target_hostname=jax-web001.evorigin.com

A data disk rather than root:

    ansible-playbook ExpandLinuxDisk.yml -e target_hostname=jax-web001.evorigin.com -e expand_disk_mount=/var/lib/docker

License
-------

MIT
