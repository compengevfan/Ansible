ConfigureWindows
================

Build-time baseline for new general-purpose Windows **member servers**. It
installs Chocolatey and desktop software, PowerShell 7, the monitoring agents,
and reboots more than once — so it is only appropriate on a host that is not yet
in service.

For a host that is already in service, or that is Tier 0 (domain controllers, the
CA), use `ConfigureMonitoringWindows` instead. That role is also included by this
one, so monitoring ends up defined in exactly one place.

What it does, in order
----------------------

1. **Refuses to run** on a monitoring-only host (see below).
2. Creates `C:\Temp`, sets the timezone to Eastern Standard Time, sets the
   execution policy to `Unrestricted` for the machine, installs the NuGet
   package provider.
3. Installs .NET Framework 4.8 **only if** the registry `Release` value is below
   `netfx_48_release`, and reboots if it installed. Server 2022 and newer already
   ship 4.8/4.8.1, so this is normally skipped.
4. Installs Chocolatey from the pinned 2.7.3 MSI if `choco.exe` is absent, then
   reboots.
5. Installs `git.install`, `notepadplusplus`, `brave`, `winscp.install`,
   `vscode`, `putty`, `windirstat`, `7zip.install` via Chocolatey.
6. Installs `dotnet_runtime_packages` via Chocolatey, if the list is non-empty.
7. Removes the old Chocolatey monitoring packages (see below).
8. Includes `ConfigureMonitoringWindows` for the Zabbix agent and
   windows_exporter.
9. Installs the latest PowerShell 7 MSI from the GitHub releases API if
   `pwsh.exe` is absent.
10. **Reboots unconditionally.**
11. Installs the `Posh-SSH` and `DupreeFunctions` PowerShell modules.

The guard against Tier 0 hosts
------------------------------

`ConfigureWindows.yml` targets `all:!MonitoringOnly`, but that pattern only
protects that one playbook. The role carries its own backstop, which fails the
run when any of these is true:

- `configure_windows_baseline_allowed` is false;
- the host is in the `MonitoringOnly` group;
- `ansible_windows_domain_role` is a primary or backup domain controller.

The domain-role check is fact-based, so a newly promoted DC is protected without
anyone remembering to update inventory.

Chocolatey monitoring packages
------------------------------

This role used to install `zabbix-agent` and
`prometheus-windows-exporter.install` from Chocolatey. Both collide with the
vendor MSIs `ConfigureMonitoringWindows` uses: choco's `zabbix-agent` aborts with
*"Cannot create a file when that file already exists"* once
`C:\ProgramData\zabbix` exists, and the exporter package wraps the same MSI, so
it exits **1603** when an equal or newer version is installed.

Both are now uninstalled here — this is where they were installed from — along
with the leftover `C:\ProgramData\zabbix` directory, which would otherwise be
picked up as a second config candidate by the monitoring role. The cleanup is
gated on Chocolatey having already been present before this run, and a failed
uninstall warns rather than stopping the play.

Requirements
------------

- WinRM connectivity and an account with local administrator rights.
  `ConfigureWindows.yml` connects with the `evoriginda` credential from Vault.
- Collections: `ansible.windows`, `community.windows`, `chocolatey.chocolatey`.
- Outbound HTTPS to `chocolatey.org`, `github.com`, `api.github.com`,
  `go.microsoft.com`, plus whatever `ConfigureMonitoringWindows` needs.
- The host must tolerate multiple reboots — at least one is unconditional.

Role Variables
--------------

See `defaults/main.yml`.

| Variable | Default | Notes |
|---|---|---|
| `configure_windows_baseline_allowed` | `true` | Set false to hard-block the baseline for a host |
| `configure_windows_monitoring_only_group` | `MonitoringOnly` | Inventory group that is refused |
| `configure_windows_blocked_domain_roles` | PDC, BDC | Matched against `ansible_windows_domain_role` |
| `netfx_48_release` | `528040` | Registry `Release` meaning 4.8; `533320` is 4.8.1 |
| `dotnet_runtime_packages` | `[]` | Modern .NET (Core) Chocolatey packages; empty skips the task |

Zabbix and windows_exporter settings are **not** here — they live in
`ConfigureMonitoringWindows/defaults/main.yml`.

Modern .NET is side-by-side with .NET Framework, not a replacement, so
`dotnet_runtime_packages` is opt-in per host via inventory or group_vars.
`defaults/main.yml` lists the package names for the current LTS (.NET 10;
.NET 8 and 9 both go end-of-support 2026-11-10).

Handlers
--------

None. The Zabbix restart handler deliberately lives only in
`ConfigureMonitoringWindows` — a second handler of the same name here would make
one `notify` fire both.

Commented-out code
------------------

`tasks/main.yml` still carries a commented-out block from an earlier design where
the role targeted `localhost`, resolved the server from `GitGetVmInfo` /
`GitConfigInfo`, built a temporary inventory entry with `add_host`, and delegated
every task to it. The `delegate_to:` comment on most tasks is a leftover of the
same. A commented-out domain-join task sits at the end.

Dependencies
------------

Includes `ConfigureMonitoringWindows`. `ConfigureWindows.yml` pairs it with
`GetVaultCreds`, `AddToZabbix` and `AddToPrometheus`. `VMwareBuildVM` includes it
for Windows builds.

Example Playbook
----------------

`ConfigureWindows.yml` in the repository root:

    ansible-playbook ConfigureWindows.yml --limit jax-app001.evorigin.com

License
-------

MIT
