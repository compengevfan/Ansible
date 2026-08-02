ProxmoxRemoveVM
===============

Stops and deletes a VM on Proxmox, and — when run in `Decom` mode — also removes
it from NetBox and DNS.

Two modes
---------

`mode` decides how much is torn down:

| `mode` | Effect |
|---|---|
| `Decom` | Stop, delete, remove from NetBox, remove the DNS A record |
| anything else | Stop and delete only; NetBox and DNS are left alone |

The second form exists for rebuilds, where the NetBox record and its IP
allocation should survive so the VM can be built again onto the same address.

`mode` has no default. It is referenced by two `when` conditions, so an
undefined `mode` fails the play at the NetBox step, after the VM is already gone.

What it does
------------

1. Upper-cases `ServerName` into `ServerNameUpper`.
2. Fetches `proxmoxroot` and `windowslocaladmin` from Vault.
3. `proxmox_kvm` `state: stopped` with `force: true`.
4. `proxmox_kvm` `state: absent` with `force: true`.
5. `NetboxRemoveVM` and `DnsDeleteARecord`, if `mode == "Decom"`.

Both Proxmox tasks set `ignore_errors: true`, so a VM that is already gone, or
already stopped, does not stop the run — but neither does a genuine API failure.
A run against an unreachable Proxmox host still reports success and still deletes
the NetBox and DNS records.

Requirements
------------

- The `community.proxmox` collection.
- The `proxmoxroot` credential in Vault. `api_host` is hard-coded to
  `pmx1.evorigin.com`.
- For `Decom`, everything `NetboxRemoveVM` and `DnsDeleteARecord` need — in
  particular, the server's build file must still exist in
  `compengevfan/vmbuildfiles`, since `DnsDeleteARecord` reads the domain from it.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Upper-cased into `ServerNameUpper` |
| `mode` | yes | `Decom` for a full teardown; see above |

`defaults/main.yml` and `vars/main.yml` are empty.

Unused values
-------------

`windowslocaladmin_cred` is fetched but never used, carried over from
`ProxmoxBuildVM`.

Dependencies
------------

Includes `GetVaultCreds`, and in `Decom` mode `NetboxRemoveVM` and
`DnsDeleteARecord`.

Example Playbook
----------------

`ProxmoxRemoveVM.yml` in the repository root:

    ansible-playbook ProxmoxRemoveVM.yml -e ServerName=jax-web001 -e mode=Decom

License
-------

MIT
