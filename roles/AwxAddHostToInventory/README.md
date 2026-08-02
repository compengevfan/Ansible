AwxAddHostToInventory
=====================

Registers a newly built server in AWX so later playbooks can target it. The host
is added to the `Linux` inventory on the AWX controller `jax-k3s001.evorigin.com`
and joined to the `AlmaLinux` and `Virtual` groups.

It is included at the end of `ProxmoxBuildVM`, so a VM built by this repository
appears in AWX without a manual step.

Only AlmaLinux is handled
-------------------------

Every task is gated on:

    when: '"Alma" in VmFileContents_JSON.VMInfo.OperatingSystem'

so a Windows or other non-AlmaLinux build runs the role and does nothing. There
is currently no Windows inventory branch.

Requirements
------------

- The `awx.awx` collection in the execution environment.
- Reachability of `jax-k3s001.evorigin.com` from wherever the role runs
  (`AwxAddHostToInventory.yml` runs it on `localhost`).
- The `awx` credential in Vault, fetched by the role itself.
- `validate_certs: no` is set on every controller call, so the controller's
  certificate is not verified.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Short server name; upper-cased into `ServerNameUpper` and used as the AWX host name |
| `VmFileContents_JSON` | no | Fetched via `GitGetVmInfo` if not already defined |

`defaults/main.yml` and `vars/main.yml` are empty. The controller host,
inventory name and group names are hard-coded in `tasks/main.yml` rather than
being variables.

| Hard-coded value | Where |
|---|---|
| `jax-k3s001.evorigin.com` | `controller_host` on all three tasks |
| `Linux` | Target inventory |
| `AlmaLinux`, `Virtual` | Groups joined, both with `preserve_existing_hosts: true` |

Dependencies
------------

Includes `GetVaultCreds` (for `awx`) and `GitGetVmInfo` (only when
`VmFileContents_JSON` is not already set).

Example Playbook
----------------

`AwxAddHostToInventory.yml` in the repository root:

    ansible-playbook AwxAddHostToInventory.yml -e ServerName=jax-web001

License
-------

MIT
