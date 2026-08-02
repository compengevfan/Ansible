ConfigureLinux
==============

Post-build baseline for AlmaLinux 9 servers. Brings a freshly cloned VM up to the
standard this lab expects: packages, PowerShell, monitoring agents, and a reboot
at the end.

The Windows counterpart is `ConfigureWindows`. Monitoring registration itself is
not done here — `ConfigureLinux.yml` follows this role with `AddToZabbix` and
`AddToPrometheus`.

What it does
------------

- Stops and disables `firewalld`.
- `dnf update -y`.
- Adds the Microsoft RHEL 9 repo, then installs `git`, `powershell`,
  `qemu-guest-agent` and `cifs-utils`.
- Adds EPEL 9.
- Replaces the old `golang-github-prometheus-node-exporter` package and its
  service with `node_exporter`, then enables and starts it (listens on 9100).
- Installs the Zabbix agent from the official Zabbix repo, sets `Server`,
  `ServerActive` and `Hostname`, enables and starts it (listens on 10050).
- Installs the `Posh-SSH` PowerShell module for all users.
- Installs the `DupreeFunctions` PowerShell module from
  `github.com/compengevfan/PowerShell` if it is not already importable.
- **Reboots unconditionally** at the end, with a 300s timeout.

Zabbix packaging
----------------

Two things here exist because EPEL also ships a `zabbix-agent`, with a different
config layout:

- `excludepkgs=zabbix*` is written into `/etc/yum.repos.d/epel.repo`, and the
  install uses `disablerepo: epel`, so the agent always comes from Zabbix's own
  repo.
- If a `zabbix-agent` package is installed but
  `/etc/zabbix/zabbix_agentd.conf` does not exist, that is the EPEL build; the
  role removes both the package and the orphaned `/etc/zabbix_agentd.conf` before
  installing the official one.

Requirements
------------

- AlmaLinux 9. The repo URLs, package names and `systemd` units are all EL9.
- SSH as root, or an account that can act as root — the tasks do not use
  `become`. `ConfigureLinux.yml` connects with the `linuxroot` credential from
  Vault.
- Collections: `community.general` (for `ini_file`), `ansible.posix` is not used
  here.
- Outbound HTTPS to `packages.microsoft.com`, `repo.zabbix.com`, EPEL mirrors and
  `github.com`.

Role Variables
--------------

See `defaults/main.yml`.

| Variable | Default | Notes |
|---|---|---|
| `zabbix_server_ip` | `192.168.0.115` | Used for both `Server` and `ServerActive` |
| `zabbix_agent_conf_path` | `/etc/zabbix/zabbix_agentd.conf` | The official package's layout |
| `zabbix_release_rpm_url` | Zabbix 7.0 EL9 release RPM | Installed with `disable_gpg_check: yes` |

`vars/main.yml` is empty.

Handlers
--------

`Restart zabbix-agent` — notified by each of the three config edits.

Two notes on behaviour
----------------------

- **`Hostname` is the short name.** The role writes `ansible_hostname`, while
  `AddToZabbix` registers the host as `ansible_fqdn`. Zabbix matches active
  checks on the agent's `Hostname`, so active checks stay unresolved until the
  two agree. `ConfigureMonitoringWindows` writes the FQDN for this reason; this
  role has not been changed to match.
- **`firewalld` is disabled outright**, so the agent port variables that the
  Windows roles use have no equivalent here — nothing is being scoped.

Dependencies
------------

None. `ConfigureLinux.yml` pairs it with `GetVaultCreds` (`linuxroot`,
`zabbixapi`), `AddToZabbix` and `AddToPrometheus`. `VMwareBuildVM` includes it
for non-Windows builds.

Example Playbook
----------------

`ConfigureLinux.yml` in the repository root, which targets the `AlmaLinux` group:

    ansible-playbook ConfigureLinux.yml --limit jax-web001

License
-------

MIT
