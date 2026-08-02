NetboxAddVM
===========

Creates a VM in NetBox from its build file, gives it an interface and an IPv4
address, sets that address as primary, and adds the matching DNS A record.

This runs **before** the VM exists on a hypervisor. `ProxmoxBuildVM` and
`VMwareBuildVM` both read their sizing and IP back out of NetBox, so NetBox is
the source of truth for the build, and this role is what populates it.

What it does
------------

1. Fetches the build file (`GitGetVmInfo`) and the network config
   (`GitConfigInfo`).
2. `netbox_virtual_machine` with the CPU, memory, platform, cluster and the
   `Datastore` / `OU` custom fields.
3. `netbox_vm_interface` named `eth1`.
4. Then one of two paths, both ending in `DnsCreateARecord`:
   - **IP supplied** — `VMInfo.IPAddress` is set: create that address, set it
     primary, add DNS.
   - **No IP supplied** — query the prefix matching `ConfigFileContents_JSON.Subnet`,
     take the first entry from NetBox's `available-ips`, create it, set it
     primary, add DNS.

Both paths are additionally gated on
`VirtualMachine.virtual_machine.primary_ip == None`, so a re-run against a VM
that already has a primary IP skips the addressing work.

Fixed values
------------

Several values are hard-coded in `tasks/main.yml` rather than being variables:

| Value | Where |
|---|---|
| `site: Amberly` | On every `netbox_virtual_machine` call |
| `cluster: C1` | On the two "Set IP as primary" calls |
| Interface name `eth1` | Interface creation and both IP assignments |

Note that the initial create uses `cluster: {{ ConfigFileContents_JSON.Cluster }}`
while the two primary-IP updates use the literal `C1`. On a build whose config
names a different cluster, the second call moves the VM to `C1`.

Requirements
------------

- The `netbox.netbox` collection, and `pynetbox` in the execution environment.
- The `netbox` credential in Vault — supplying `url`, `token` for the modules and
  `api_token` for the raw `uri` calls, which pass it as the `Authorization`
  header verbatim.
- `validate_certs: no` throughout, so the NetBox certificate is not verified.
- The site, cluster, platform and the `Datastore` / `OU` custom fields must
  already exist in NetBox. The platform name comes from
  `VMInfo.OperatingSystem`, and the build roles later read
  `platform.custom_fields.VM_Template` off it — so the platform must carry that
  field too.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Upper-cased into `ServerNameUpper`, which is the NetBox VM name |
| `netbox_cred` | yes | Not fetched here — `NetboxAddVM.yml` fetches it in a preceding play |
| `VmFileContents_JSON` | no | Fetched if not already defined |
| `ConfigFileContents_JSON` | no | Fetched if not already defined |

`defaults/main.yml` and `vars/main.yml` are empty.

Unlike most roles here, this one does **not** include `GetVaultCreds` itself. Run
it from `NetboxAddVM.yml`, or fetch the `netbox` credential first.

Memory units
------------

`VMInfo.RAM` is treated as GB and multiplied by 1024 for NetBox's `memory` field,
which is MB. The build roles then read that MB value straight back out for
Proxmox and vCenter.

Dependencies
------------

Includes `GitGetVmInfo`, `GitConfigInfo` and `DnsCreateARecord`.

Example Playbook
----------------

`NetboxAddVM.yml` in the repository root:

    ansible-playbook NetboxAddVM.yml -e ServerName=jax-web001

License
-------

MIT
