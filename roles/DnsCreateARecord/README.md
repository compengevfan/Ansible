DnsCreateARecord
================

Creates an A record in Microsoft DNS for a newly built server. `NetboxAddVM`
calls it once an IP has been assigned, so the NetBox allocation and DNS stay in
step.

How it connects
---------------

The DNS server is not in inventory. The role fetches the `evorigindns`
credential from Vault, which carries the server name alongside the username and
password, and builds an inventory entry for it on the fly:

    - add_host:
        name: "{{ evorigindns_cred.dnsservername }}"
        groups: dns_host
        ansible_connection: winrm
        ansible_port: 5985
        ansible_winrm_transport: ntlm

The record is then written with `community.windows.win_dns_record` delegated to
that host.

Requirements
------------

- The `community.windows` collection, and `pywinrm` in the execution
  environment.
- WinRM over **HTTP on 5985 with NTLM** to the DNS server, and a service account
  allowed to write to the zone.
- The `evorigindns` credential in Vault, with a `dnsservername` key. The role
  fetches it itself.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerNameUpper` | yes | Record name. The role does **not** upper-case it — the caller must supply it already upper-cased |
| `IpAddress` | yes | Record value |
| `Domain` | yes | DNS zone |

`defaults/main.yml` and `vars/main.yml` are empty.

Only evorigin.com is wired up
-----------------------------

The `add_host` task is gated on `when: Domain == "evorigin.com"`. For any other
domain the host is never added, and the `delegate_to` on the record task then
fails. Adding a second domain means adding a second credential and a second
`add_host` task.

Dependencies
------------

Includes `GetVaultCreds` (for `evorigindns`). Called by `NetboxAddVM` on both the
supplied-IP and the auto-allocated-IP paths.

Example Playbook
----------------

`CreateDnsARecord.yml` in the repository root:

    ansible-playbook CreateDnsARecord.yml \
      -e ServerNameUpper=JAX-WEB001 -e IpAddress=192.168.0.50 -e Domain=evorigin.com

License
-------

MIT
