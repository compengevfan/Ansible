ConfigureMonitoringWindows
==========================

Installs and configures monitoring agents on a Windows server that is **already
built and in service** — domain controllers, the certificate authority, and any
other host where the full `ConfigureWindows` baseline would be inappropriate.

It is also included by the `ConfigureWindows` role, so a new member server build
and a monitoring-only run produce the same result. Monitoring is defined once,
here.

Specifically it:

- Installs the Zabbix agent from the official Zabbix MSI (if not already present)
- Installs `windows_exporter` from the official prometheus-community MSI (if not
  already present)
- Enforces `Server`, `ServerActive` and `Hostname` in the Zabbix agent config
- Opens inbound TCP 10050 and 9182, scoped to the allowed source addresses
- Ensures both services are set to auto-start and are running

What it deliberately does **not** do
------------------------------------

This role is the counterpart to `ConfigureWindows`, which is a build-time
baseline for new general-purpose member servers. On an in-service Tier 0 host
that baseline is unsafe, so this role omits:

- **Any reboot.** `ConfigureWindows` has three, one unconditional. Against a play
  targeting several domain controllers that means a simultaneous AD/DNS outage.
- **Chocolatey and the public community feed.** Agents come from vendor MSIs.
- **`Set-ExecutionPolicy Unrestricted -Scope LocalMachine`.**
- **.NET Framework 4.8 install.** Server 2022 already ships it, and an
  in-service host does not need a framework upgrade to be monitored.
- **Desktop software** (browser, VS Code, PuTTY, WinSCP, and so on).

Requirements
------------

- WinRM connectivity, and an account with local administrator rights on the
  target. `ConfigureMonitoringWindows.yml` connects with the `evoriginda`
  credential from Vault.
- Collections: `ansible.windows`, `community.windows`.
- Outbound HTTPS from the target to `cdn.zabbix.com` and `github.com` for the
  initial install. Subsequent runs download nothing.

Role Variables
--------------

See `defaults/main.yml`. The ones most likely to need changing:

| Variable | Default | Notes |
|---|---|---|
| `zabbix_server_ip` | `192.168.0.115` | Used for both `Server` and `ServerActive` |
| `zabbix_agent_version` | `7.0.27` | Must not be newer than the Zabbix server |
| `windows_exporter_version` | `0.31.8` | |
| `zabbix_agent_allowed_source` | `{{ zabbix_server_ip }}` | Firewall `remoteip` scope |
| `prometheus_allowed_source` | `any` | Set to your scraper's IP to tighten |
| `monitoring_download_dir` | `C:\Windows\Temp` | Installers are staged here and removed afterwards |

Versions are pinned rather than resolved to "latest" at run time so a run is
repeatable and auditable. To confirm the Zabbix server version before bumping
`zabbix_agent_version`:

    curl -s -X POST http://zabbix.evorigin.com/zabbix/api_jsonrpc.php \
      -H 'Content-Type: application/json-rpc' \
      -d '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}'

Relationship to Chocolatey
--------------------------

This role never touches Chocolatey — that is the point of it, since Chocolatey
is not an option on domain controllers.

`ConfigureWindows` used to install `zabbix-agent` and
`prometheus-windows-exporter.install` from Chocolatey, which collides with the
MSIs used here: choco's `zabbix-agent` aborts with *"Cannot create a file when
that file already exists"* once `C:\ProgramData\zabbix` exists, and the exporter
package wraps this very same MSI, so it exits **1603** when an equal or newer
version is installed. Both packages have been dropped from the `ConfigureWindows`
software list, and **`ConfigureWindows` removes any leftovers itself** before
including this role, since that is where they were installed from.

A host that only ever runs `ConfigureMonitoringWindows` is unaffected — it never
had Chocolatey in the first place.

Two notes on behaviour
----------------------

- **Hostname is the FQDN.** `AddToZabbix` registers hosts as `ansible_fqdn`, and
  Zabbix matches active checks on the agent's `Hostname` value. This role writes
  the FQDN so the two agree. `ConfigureWindows` and `ConfigureLinux` write
  `ansible_hostname` (the short name) and so leave active checks unresolved —
  that is a pre-existing issue in those roles, not something this role changes.
- **The windows_exporter MSI adds its own unscoped firewall exception** for 9182
  at install time. Windows allows traffic if any rule matches, so
  `prometheus_allowed_source` only becomes effective once that vendor rule is
  disabled.

Dependencies
------------

None. `ConfigureMonitoringWindows.yml` pairs it with `GetVaultCreds` (for the
`evoriginda` and `zabbixapi` credentials) and `AddToZabbix` (to register the
host), both used unmodified.

Example Playbook
----------------

See `ConfigureMonitoringWindows.yml` in the repository root. Scope the run with
an AWX limit, or:

    ansible-playbook ConfigureMonitoringWindows.yml --limit dc01.evorigin.com

License
-------

MIT
