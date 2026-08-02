ProxmoxBuildVM
==============

Builds a VM on Proxmox by cloning a template, sizing it and setting its network
from what NetBox already knows, starting it, and registering it in AWX.

NetBox is the source of truth here: `NetboxAddVM` must have run first. This role
reads the VM's vCPUs, memory, datastore, platform and primary IP back out of the
NetBox API rather than out of the build file.

What it does
------------

1. Fetches `netbox`, `proxmoxroot` and `windowslocaladmin` from Vault.
2. Fetches the build file (`GitGetVmInfo`) and network config (`GitConfigInfo`).
3. Queries NetBox for the VM, then for its platform, then for the prefix
   containing its primary IP.
4. Runs `files/Subnet.py` on `localhost` to turn the CIDR prefix length into a
   dotted netmask.
5. Clones `platform.custom_fields.VM_Template` to `ServerNameUpper` on node
   `pmx1`, into the datastore from the VM's `Datastore` custom field, as `qcow2`,
   with a 500s timeout.
6. Updates the clone with cores/vcpus/memory, search domain, both nameservers,
   and `ipconfig0` (address plus gateway) — i.e. cloud-init style configuration.
7. Starts the VM.
8. Includes `AwxAddHostToInventory`.

Requirements
------------

- The `community.proxmox` collection, plus `netbox` reachability for the `uri`
  calls (`validate_certs: no` throughout).
- `/usr/bin/python` on the control node for `Subnet.py`, which is dispatched with
  `delegate_to: localhost`.
- The template must be cloud-init capable — `ipconfig`, `nameservers` and
  `searchdomains` only take effect on a guest that reads cloud-init.
- `NetboxAddVM` must have run, and the VM must have a primary IP: the role
  indexes `vmInfo.json.results[0].primary_ip.address` with no guard.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Upper-cased into `ServerNameUpper` |
| `VmFileContents_JSON` | no | Fetched if not already defined |
| `ConfigFileContents_JSON` | no | Fetched if not already defined |

`defaults/main.yml` and `vars/main.yml` are empty. Proxmox targeting is
hard-coded in `tasks/main.yml`:

| Hard-coded value | Where |
|---|---|
| `pmx1.evorigin.com` | `api_host` on all three calls |
| `pmx1` | `node` on all three calls |
| `qcow2` | Clone disk format |

Windows is not handled
----------------------

The whole clone block is titled "Clone a virtual machine from Linux template",
and the `when: not platform.json.name is search("Windows")` that would restrict
it is commented out at the bottom of the file. As it stands the role runs the
Linux path for any platform. `VMwareBuildVM` is the role with both branches.

Nothing here calls `ConfigureLinux` either — a Proxmox build stops after the VM
is registered in AWX, and the baseline is applied by running `ConfigureLinux.yml`
afterwards.

Unused values
-------------

`windowslocaladmin_cred`, the `prefix` query and `subnetReturn` are all fetched
but never used by this role; they are carried over from `VMwareBuildVM`, where
the netmask is needed because vCenter customisation takes one.

Dependencies
------------

Includes `GetVaultCreds`, `GitGetVmInfo`, `GitConfigInfo` and
`AwxAddHostToInventory`.

Example Playbook
----------------

`ProxmoxBuildVM.yml` in the repository root:

    ansible-playbook ProxmoxBuildVM.yml -e ServerName=jax-web001

License
-------

MIT
