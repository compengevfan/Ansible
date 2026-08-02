DnsDeleteARecord
================

Removes a server's A record from Microsoft DNS at decom time. The inverse of
`DnsCreateARecord`, and called by `ProxmoxRemoveVM` when it runs in `Decom` mode.

Unlike the create role, this one does not take the domain as a parameter — it
resolves it from the server's build files, via `GitGetVmInfo` and then
`GitConfigInfo`, and uses `ConfigFileContents_JSON.Domain`.

How it connects
---------------

Same approach as `DnsCreateARecord`: the `evorigindns` credential from Vault
carries the DNS server name, an inventory entry is built with `add_host`, and
`community.windows.win_dns_record` runs against it with `state: absent`.

Requirements
------------

- The `community.windows` collection, and `pywinrm` in the execution
  environment.
- WinRM over **HTTP on 5985 with NTLM** to the DNS server, and a service account
  allowed to write to the zone.
- The build file for the server must still exist in `compengevfan/vmbuildfiles`,
  since the domain is read from it. If it has already been deleted, this role
  fails at the `GitGetVmInfo` step.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Used to fetch the build file |
| `ServerNameUpper` | yes | Record name. This role does **not** set it — the caller must. `ProxmoxRemoveVM` sets it before including this role |
| `VmFileContents_JSON` | no | Fetched if not already defined |
| `ConfigFileContents_JSON` | no | Fetched if not already defined |

`defaults/main.yml` and `vars/main.yml` are empty.

Only evorigin.com is wired up
-----------------------------

The `add_host` task is gated on
`when: ConfigFileContents_JSON.Domain == "evorigin.com"`. For any other domain
the host is never added and the `delegate_to` on the delete task fails.

Cosmetic note
-------------

The delete task is still named "Add the A Record", copied from
`DnsCreateARecord`; only `state: absent` distinguishes it. The `no_log: true` on
the `add_host` task is commented out here but active in the create role.

Dependencies
------------

Includes `GetVaultCreds` (`evorigindns`), `GitGetVmInfo` and `GitConfigInfo`.

Example Playbook
----------------

There is no dedicated playbook for this role. It is included by
`ProxmoxRemoveVM`:

    - hosts: localhost
      connection: local
      tasks:
        - set_fact:
            ServerNameUpper: "{{ ServerName | upper }}"
        - include_role:
            name: DnsDeleteARecord

License
-------

MIT
