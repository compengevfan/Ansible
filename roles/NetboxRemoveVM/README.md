NetboxRemoveVM
==============

Deletes a VM from NetBox. The inverse of `NetboxAddVM`, called by
`ProxmoxRemoveVM` when it runs in `Decom` mode.

Deleting the virtual machine object cascades in NetBox, so the interface and the
IP address created by `NetboxAddVM` go with it — there are no separate cleanup
tasks. The DNS record does **not** go with it; that is `DnsDeleteARecord`'s job,
and `ProxmoxRemoveVM` calls both.

Requirements
------------

- The `netbox.netbox` collection, and `pynetbox` in the execution environment.
- The `netbox` credential in Vault, fetched by the role itself.
- `validate_certs: no`, so the NetBox certificate is not verified.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Upper-cased into `ServerNameUpper`, the NetBox VM name |

`defaults/main.yml` and `vars/main.yml` are empty.

Notes on behaviour
------------------

- The result is registered as `VirtualMachine` but nothing reads it, and the
  module does not fail on a VM that was already gone — so a re-run is harmless
  and a typo in `ServerName` is silent.
- Unlike `NetboxAddVM`, this role fetches its own credential, so it can be run
  standalone.

Dependencies
------------

Includes `GetVaultCreds` (for `netbox`).

Example Playbook
----------------

`NetboxRemoveVM.yml` in the repository root:

    ansible-playbook NetboxRemoveVM.yml -e ServerName=jax-web001

License
-------

MIT
