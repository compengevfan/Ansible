VMwareBuildVM
=============

Builds a VM on vSphere by cloning a template, customising it, powering it on, and
then applying the OS baseline — `ConfigureWindows` for Windows guests,
`ConfigureLinux` for everything else. It is the most complete build path in this
repository; the Proxmox equivalent stops after the VM is registered in AWX.

As with `ProxmoxBuildVM`, NetBox is the source of truth: `NetboxAddVM` must have
run first, and the sizing, datastore, platform and primary IP are read back out
of the NetBox API rather than out of the build file.

What it does
------------

1. Fetches `netbox`, `vcenter` and `windowslocaladmin` from Vault.
2. Fetches the build file (`GitGetVmInfo`) and network config (`GitConfigInfo`).
3. Queries NetBox for the VM, its platform and the prefix containing its primary
   IP; runs `files/Subnet.py` on `localhost` to convert the prefix length into a
   dotted netmask.
4. Clones `platform.custom_fields.VM_Template` into `/EvOrigin/Workers` on
   datacenter `DC1`, powered off, with the CPU/memory from NetBox and one NIC on
   the config's port group. Windows and Linux have separate clone tasks,
   selected on whether the platform name contains "Windows".
5. Sets the NIC to connect at power on — templates commonly leave it
   disconnected, which would break customisation.
6. Powers on with `wait_for_customization` and `wait_for_ip_address`. Linux runs
   a trivial `script_text`; Windows runs
   `C:\Windows\Temp\ConfigureRemotingForAnsible.ps1 -ForceNewSSLCert -EnableCredSSP`
   as a `runonce`, which is what makes the guest reachable over WinRM.
7. Upgrades VMware Tools (Windows only).
8. Includes `ConfigureWindows` or `ConfigureLinux`.

Requirements
------------

- The `community.vmware` collection, and `pyvmomi` in the execution environment.
- The `vcenter` credential in Vault, supplying `servername`, `username` and
  `password`. `validate_certs: no` throughout.
- **Windows templates must already contain**
  `C:\Windows\Temp\ConfigureRemotingForAnsible.ps1`. Nothing in this role puts it
  there, and without it the `ConfigureWindows` include cannot connect.
- `NetboxAddVM` must have run, and the VM must have a primary IP: the role
  indexes `vmInfo.json.results[0].primary_ip.address` with no guard.
- `/usr/bin/python` on the control node for `Subnet.py`, dispatched with
  `delegate_to: localhost`.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Upper-cased into `ServerNameUpper`, the VM name |
| `VmFileContents_JSON` | no | Fetched if not already defined |
| `ConfigFileContents_JSON` | no | Fetched if not already defined |

`defaults/main.yml` and `vars/main.yml` are empty. vSphere targeting is
hard-coded in `tasks/main.yml`:

| Hard-coded value | Where |
|---|---|
| `DC1` | `datacenter` on every task |
| `/EvOrigin/Workers` | Clone folder |
| `Network adapter 1` | The NIC whose `start_connected` is set |

The clone tasks take `cluster` from `ConfigFileContents_JSON.Cluster` while the
power-on tasks take it from `vmInfo.json.results[0].cluster.name` — the NetBox
value. `NetboxAddVM` writes `C1` into NetBox on its primary-IP update, so these
two only agree when the config's cluster is also `C1`.

Windows vs. Linux
-----------------

The branch is `platform.json.name is search("Windows")` — the **NetBox platform
name**, not the build file's `OperatingSystem`. A platform whose name does not
contain "Windows" takes the Linux path regardless of what it actually runs.

The Windows clone passes `customization.password` from `windowslocaladmin_cred`,
setting the local administrator password during customisation. The Linux clone
sets DNS servers and suffix instead.

Only the Windows clone task carries `delegate_to: localhost`; the Linux one does
not. Both are `hosts: localhost` in the playbook, so this makes no practical
difference today.

Dependencies
------------

Includes `GetVaultCreds`, `GitGetVmInfo`, `GitConfigInfo`, and then either
`ConfigureWindows` or `ConfigureLinux`.

Note that `ConfigureWindows` refuses to run on a `MonitoringOnly` host or a
domain controller — which is correct here, since a freshly cloned VM is neither,
but it does mean this role cannot be used to rebuild one.

Example Playbook
----------------

`VMwareBuildVM.yml` in the repository root:

    ansible-playbook VMwareBuildVM.yml -e ServerName=jax-web001

License
-------

MIT
