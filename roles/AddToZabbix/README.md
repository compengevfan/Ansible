AddToZabbix
===========

Registers the target host in Zabbix if it is not already there, using the Zabbix
API. The counterpart to `AddToPrometheus`, and included at the end of
`ConfigureLinux.yml`, `ConfigureWindows.yml` and `ConfigureMonitoringWindows.yml`
— all of which install an agent but do not tell the server about it.

The host is created with a passive agent interface on 10050 addressed by DNS
(`useip: 0`, `dns: ansible_fqdn`), in the host group and with the template that
`zabbix_os_map` selects from `ansible_system`.

What it does
------------

1. Fails if `ansible_system` is not in `zabbix_os_map`.
2. Works out an IPv4 address for the interface: `ansible_default_ipv4.address`
   first, then the first entry of `ansible_all_ipv4_addresses` (Linux), then the
   first IPv4-looking entry of `ansible_ip_addresses` (Windows). Fails if none of
   those produce one.
3. `host.get` for `ansible_fqdn`. If it exists, nothing further happens.
4. Otherwise `hostgroup.get` and `template.get`, each failing with a named
   message if the object is missing, then `host.create`.
5. Fails if `host.create` returned an API error, and reports the new host ID
   otherwise.

All API calls run on the control node via `delegate_to: localhost`.

The connection-variable override
--------------------------------

The calling play sets `ansible_user` / `ansible_password` from a Vault credential
that `GetVaultCreds` stored as a fact on the **target** host. Ansible re-templates
those connection vars for the delegate on every `delegate_to` task, and
`localhost` never had that fact, so the play fails before the API call is made.

The whole API block therefore runs under:

    vars:
      ansible_connection: local
      ansible_user: root
      ansible_password: ''

so nothing needs templating. That is why the block exists; it is not about
privileges.

Requirements
------------

- The calling play must fetch the **`zabbixapi`** credential via `GetVaultCreds`
  — the role sends `zabbixapi_cred.token` as a bearer token.
- The control node must be able to reach `zabbix_api_url`.
- Facts must be gathered on the target: the role reads `ansible_system`,
  `ansible_fqdn` and the address facts.
- The host group and template named by `zabbix_os_map` must already exist in
  Zabbix. The role fails rather than creating them.
- Target hosts must resolve in DNS from the Zabbix server, since the interface is
  created with `useip: 0`.

Role Variables
--------------

See `defaults/main.yml`.

| Variable | Default | Notes |
|---|---|---|
| `zabbix_api_url` | `http://zabbix.evorigin.com/zabbix` | `/api_jsonrpc.php` is appended |
| `zabbix_api_validate_certs` | `false` | |
| `zabbix_os_map` | Win32NT / Linux | `ansible_system` → template and host group |

Defaults for `zabbix_os_map`:

| `ansible_system` | Template | Host group |
|---|---|---|
| `Win32NT` | `Windows by Zabbix agent` | `Windows` |
| `Linux` | `Linux by Zabbix agent` | `Linux servers` |

Extend the map to support another OS family.

Notes on behaviour
------------------

- **Registration only.** An existing host is left exactly as it is — the role
  never updates its group, template or interface. To change those, edit the host
  in Zabbix or delete it and re-run.
- The host is registered as `ansible_fqdn`. Zabbix matches active checks on the
  agent's own `Hostname` value, so the agent config must agree.
  `ConfigureMonitoringWindows` writes the FQDN; `ConfigureLinux` and
  `ConfigureWindows` write the short name, which leaves active checks unresolved
  on those hosts.
- The IPv4 address is only used for the interface record. Because `useip: 0`,
  Zabbix polls the DNS name and the address is informational.
- `no_log: true` is set on the lookups but is commented out on `host.create`, so
  a failure there shows the request. The failure message says to remove `no_log`
  from that task, which is already the case.

Dependencies
------------

None. Callers pair it with `GetVaultCreds` for the `zabbixapi` credential.

Example Playbook
----------------

See `ConfigureLinux.yml`, `ConfigureWindows.yml` or
`ConfigureMonitoringWindows.yml` in the repository root, each of which ends with:

    - name: Add host to Zabbix
      include_role:
        name: AddToZabbix

License
-------

MIT
