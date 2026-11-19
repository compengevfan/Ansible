PatchLinux
==========

Monthly patching for the AlmaLinux hosts. Applies **every** available update
with dnf, then reboots the hosts that need it in a safe order, one at a time,
checking each one before moving on.

It is meant to run on a schedule from Ascender, which brings one complication:
Ascender runs as a pod on `jax-k3s001l`, so rebooting that VM mid-run would kill
the job that is doing the patching. That host is updated like the rest, but
given a **delayed** reboot that fires a few minutes after the job has finished.

How a run goes
--------------

`PatchLinux.yml` is five plays:

1. **GetCredentials** — `linuxroot` from Vault, for every host.
2. **Update** (`tasks/main.yml`, all hosts at once):
   - `dnf upgrade` of every package, kernel included.
   - `dnf needs-restarting -r` to see whether a reboot is needed.
   - Each host that needs one goes into a reboot group with `group_by`.
3. **Reboot now** (`tasks/reboot.yml`, group `patch_linux_reboot_now`,
   `serial: 1`): every host not named in either list below.
4. **Reboot last** (`tasks/reboot.yml`, group `patch_linux_reboot_last`,
   `serial: 1`): the hosts the others depend on, `jax-dock001l` (Gitea) and
   `jax-tail001l` (Tailscale), in inventory order.
5. **Scheduled reboot** (`tasks/schedule_reboot.yml`, group
   `patch_linux_reboot_scheduled`): `shutdown -r +5` on `jax-k3s001l`. This
   is the last thing the job does, so the reboot lands after Ascender has
   saved the result.

Hosts that don't need a reboot go into no group and are only updated.

### Checks after each reboot

- `ansible.builtin.reboot` waits up to `patch_linux_reboot_timeout` for SSH.
- `systemctl is-system-running --wait` waits for the boot to finish. A
  `degraded` result lists the failed units as a warning, or stops the run
  when `patch_linux_fail_on_degraded` is true.
- `k3s` and `docker` must reach `active`, where they are installed and enabled.
  The next host may depend on them (Gitea is a Docker container).
- The running kernel is compared with `grubby --default-kernel`, and a
  mismatch is reported.

### When something fails

- **During the update play:** a host whose dnf run fails drops out of the rest
  of the run. The other hosts carry on, and the job is marked failed.
- **During a reboot play:** the reboot plays use `serial: 1` and
  `max_fail_percentage: 0`. A host that doesn't come back, or whose services
  don't start, **stops the whole run**, and no further host is rebooted.
  That includes the scheduled reboot of `jax-k3s001l`, which is left updated
  but not rebooted until you deal with it.

Role Variables
--------------

See `defaults/main.yml`. Host names are short names, matched without regard to
case against the inventory name with the domain removed.

| Variable | Default | Notes |
|---|---|---|
| `patch_linux_force_reboot` | `false` | Reboot every host, even ones that don't need it |
| `patch_linux_scheduled_reboot_hosts` | `[jax-k3s001l]` | Hosts the job runs on; get a delayed reboot |
| `patch_linux_scheduled_reboot_delay` | `5` | Minutes until the delayed reboot |
| `patch_linux_reboot_last_hosts` | `[jax-dock001l, jax-tail001l]` | Rebooted after everything else |
| `patch_linux_reboot_timeout` | `900` | Seconds to wait for a host to come back |
| `patch_linux_wait_for_services` | `[k3s, docker]` | Must be active after a reboot, where enabled |
| `patch_linux_fail_on_degraded` | `false` | Stop the run on a degraded boot instead of warning |

Requirements
------------

- AlmaLinux 9 (any dnf-based EL9 works). `dnf-plugins-core`, which provides
  `needs-restarting`, is installed if it is missing.
- SSH as root via the `linuxroot` credential, like `ConfigureLinux`. No
  `become`.
- Every host in the `AlmaLinux` group must be reachable from the Ascender
  execution pod. That includes `DIO-MON001L`, which is at DigitalOcean.

What it does not do
-------------------

- **No snapshots.** Recovery is the weekly Proxmox backup.
- **No Zabbix maintenance window.** Reboots will raise and clear availability
  alerts.
- **k3s itself is not updated.** k3s is installed from its install script, not
  from a dnf repo. Only `k3s-selinux` comes from dnf. k3s versions are
  upgraded separately (quarterly, per the HomeLab Updates list).
- **Container images are not updated.** Those go through the `k3s` repo and
  Docker.

Scheduling in Ascender
----------------------

1. Create a job template:
   - Playbook: `PatchLinux.yml`.
   - Inventory: the one that holds the `AlmaLinux` group.
   - Credential: the Vault lookup credential the other templates use.
2. Add a monthly schedule to it, at a time that stays clear of the Monday
   1–4 AM backup window, for example the first Saturday at 03:00.

Run it once by hand first, ideally with `--check` (Ascender's "Check" job type).
That shows what would be updated and who would reboot, without changing
anything.

Example Playbook
----------------

`PatchLinux.yml` in the repository root. All hosts:

    ansible-playbook PatchLinux.yml

One host, for a test:

    ansible-playbook PatchLinux.yml -e target_hostname=jax-wkn001l.evorigin.com

License
-------

MIT
