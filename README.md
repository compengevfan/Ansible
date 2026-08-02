Ansible
=======

The Ansible content behind the **evorigin.com** home lab: VM provisioning and
decommissioning across Proxmox and vSphere, Windows and Linux post-build
baselines, monitoring onboarding, DNS and IPAM bookkeeping, certificate
enrolment, and a handful of Brocade FC switch operations.

Everything here is designed to be run from **AWX** (the controller is
`jax-k3s001.evorigin.com`), which is why most playbooks take their parameters as
extra vars and why there is no inventory or `ansible.cfg` in the repository.

Layout
------

    *.yml, *.yaml      Playbooks. Each is thin - one or two plays that fetch
                       credentials and then include a role.
    roles/             Where all the actual work lives.

There are no `group_vars`, `host_vars`, `inventory` or `ansible.cfg` files.
Inventory comes from AWX; secrets come from Vault; per-server build definitions
come from a separate GitHub repository (see below).

How a build hangs together
--------------------------

Three external systems, in order, hold the state a build needs:

1. **`compengevfan/vmbuildfiles` on GitHub** — one JSON file per server (CPU,
   RAM, datastore, OU, OS, network name) plus one per network config (domain,
   subnet, gateway, DNS servers, cluster, port group). `GitGetVmInfo` and
   `GitConfigInfo` fetch them.
2. **NetBox** — `NetboxAddVM` creates the VM object from those files and either
   records the requested IP or allocates the next free one from the prefix, then
   adds the DNS A record.
3. **The hypervisor** — `ProxmoxBuildVM` or `VMwareBuildVM` clones the template
   named by the NetBox platform's `VM_Template` custom field and sizes the VM
   from what NetBox holds.

So NetBox is the source of truth at clone time, and the build files are the
source of truth for NetBox. A build in the wrong order does not work.

A typical Proxmox build is therefore:

    NetboxAddVM.yml  ->  ProxmoxBuildVM.yml  ->  ConfigureLinux.yml

vSphere is a single step, because `VMwareBuildVM` includes the baseline role
itself:

    NetboxAddVM.yml  ->  VMwareBuildVM.yml

And a decom is:

    ProxmoxRemoveVM.yml -e mode=Decom

which tears down the VM, the NetBox object and the DNS record together.

Credentials
-----------

No credential is stored in this repository. Every playbook that needs one starts
by including `GetVaultCreds`, which reads it from HashiCorp Vault under
`HomeLabSecrets/` and sets it as a fact:

    - name: Obtain Credentials
      include_role:
        name: GetVaultCreds
      vars:
        includecred:
          - evoriginda
          - zabbixapi

`GetVaultCreds/README.md` lists every available credential name, the fact it
sets, and its Vault path. Vault itself is deployed by the `VaultDeploy` role.

Playbooks
---------

### Provisioning and decom

| Playbook | Role | What it does |
|---|---|---|
| `NetboxAddVM.yml` | `NetboxAddVM` | Create the VM, interface, IP and DNS record in NetBox |
| `NetboxRemoveVM.yml` | `NetboxRemoveVM` | Delete the VM from NetBox |
| `ProxmoxBuildVM.yml` | `ProxmoxBuildVM` | Clone, size and start a VM on Proxmox; register it in AWX |
| `ProxmoxRemoveVM.yml` | `ProxmoxRemoveVM` | Stop and delete a Proxmox VM; full decom with `-e mode=Decom` |
| `VMwareBuildVM.yml` | `VMwareBuildVM` | Clone, customise and power on a vSphere VM, then run the OS baseline |
| `AwxAddHostToInventory.yml` | `AwxAddHostToInventory` | Add a host to the AWX `Linux` inventory |

### Configuration and monitoring

| Playbook | Role | What it does |
|---|---|---|
| `ConfigureLinux.yml` | `ConfigureLinux` | AlmaLinux 9 baseline, then Zabbix and Prometheus onboarding |
| `ConfigureWindows.yml` | `ConfigureWindows` | Windows member server baseline, then Zabbix and Prometheus onboarding |
| `ConfigureMonitoringWindows.yml` | `ConfigureMonitoringWindows` | Monitoring agents only, for in-service and Tier 0 Windows hosts |

### DNS, certificates, infrastructure

| Playbook | Role | What it does |
|---|---|---|
| `CreateDnsARecord.yml` | `DnsCreateARecord` | Add an A record to Microsoft DNS |
| `CreateMsCaCertificate.yml` | `CreateMsCaCertificate` | Enrol a certificate from the Microsoft CA and export it as pfx/key/crt |
| `VaultDeploy.yml` | `VaultDeploy` | Install and configure HashiCorp Vault |
| `GetVaultCreds.yml` | `GetVaultCreds` | Fetch credentials on their own, for testing |
| `GitGetVmInfo.yml` | `GitGetVmInfo` | Fetch and show a server's build file |

### Brocade FC switches

These are the oldest content here. They talk to FOS over `raw` SSH, run with
`gather_facts: False`, and take the switch as `-e target_hostname=<switch>`.
Their `fail` messages are prefixed with `Order 66`, which is how the calling
automation recognises an operator-actionable failure.

| Playbook | Role | What it does |
|---|---|---|
| `BrocadePortUp.yml` | `BrocadePortUp` | Persistently enable a port and name it to convention |
| `BrocadePortDown.yml` | `BrocadePortDown` | Persistently disable a server's port and rename it back |
| `BrocadeCopyFEPorts.yml` | `BrocadeCopyFEPorts` | Read the array front-end ports out of a server's existing zones |
| `BrocadeZoning.yml` | `BrocadeZoning` | Create the alias and two zones and enable the config |
| `BrocadeDecom.yml` | `BrocadeDecom` | Remove a server's zones and alias |

### Dell iDRAC

Neither of these uses a role.

| Playbook | What it does |
|---|---|
| `idracReset.yaml` | Reset the iDRACs on `rac-pmx1/2/3`, which are listed inline in the playbook |
| `idrac-maint.yaml` | Clear the SEL, clear the LC job queue and reset the iDRAC, against whatever inventory is passed |

### Scratch

`test.yml` and `Test-Powershell.yml` are working files, not part of any workflow.
`test.yml` fetches a Vault credential and runs `uptime`; `Test-Powershell.yml`
checks that a Vault credential can be turned into a `PSCredential` under `pwsh`
in an AWX execution environment. `Test-Powershell.yml` has a known quoting bug —
`"{{ test_cred }}.password"` renders the whole dictionary and then a literal
`.password`.

Roles
-----

Each role has its own README with its variables, requirements and caveats.

| Role | Purpose |
|---|---|
| `AddToPrometheus` | Write a per-host file-SD target file for Prometheus |
| `AddToZabbix` | Register the host in Zabbix via the API |
| `AwxAddHostToInventory` | Add a host to the AWX `Linux` inventory and its groups |
| `AwxRemoveHostFromInventory` | Remove a host from the AWX `Linux` inventory |
| `BrocadeCopyFEPorts` | Read array FE ports from an existing zone pair |
| `BrocadeDecom` | Remove zones and alias from a Brocade switch |
| `BrocadePortDown` | Persistently disable and rename a switch port |
| `BrocadePortUp` | Persistently enable and name a switch port |
| `BrocadeZoning` | Create alias and zones and enable the config |
| `ConfigureLinux` | AlmaLinux 9 post-build baseline |
| `ConfigureMonitoringWindows` | Zabbix agent and windows_exporter, no reboot, safe on Tier 0 |
| `ConfigureWindows` | Windows member server post-build baseline |
| `CreateMsCaCertificate` | `certreq` enrolment and pfx/key/crt export |
| `DnsCreateARecord` | Add an A record to Microsoft DNS |
| `DnsDeleteARecord` | Remove an A record from Microsoft DNS |
| `GetVaultCreds` | Fetch credentials from HashiCorp Vault |
| `GitConfigInfo` | Fetch a network config definition from GitHub |
| `GitGetVmInfo` | Fetch a server build definition from GitHub |
| `NetboxAddVM` | Create the VM, interface, IP and DNS record |
| `NetboxRemoveVM` | Delete the VM from NetBox |
| `ProxmoxBalanceCluster` | **Scaffold only — no tasks.** Intended to rebalance VMs across Proxmox nodes |
| `ProxmoxBuildVM` | Clone, size and start a VM on Proxmox |
| `ProxmoxRemoveVM` | Stop and delete a Proxmox VM, optionally full decom |
| `VMwareBuildVM` | Clone, customise and power on a vSphere VM, then baseline it |
| `VaultDeploy` | Install and configure HashiCorp Vault |

Windows baselines: which one
----------------------------

This is the distinction most likely to matter:

- **`ConfigureWindows`** is a *build-time* baseline for new general-purpose
  member servers. It installs Chocolatey and desktop software, sets the execution
  policy to `Unrestricted`, and reboots more than once. It refuses to run on a
  host in the `MonitoringOnly` group or on a domain controller — the check is
  fact-based, so a newly promoted DC is protected without inventory changes.
- **`ConfigureMonitoringWindows`** is for hosts already in service, including
  domain controllers and the CA. Agents come from vendor MSIs, nothing reboots,
  and Chocolatey is never involved. `ConfigureWindows` includes it, so monitoring
  is defined in exactly one place.

Conventions used throughout
---------------------------

- **Server names are upper-cased.** Roles set `ServerNameUpper` from `ServerName`
  and use that for NetBox, AWX, DNS and the hypervisor. Two roles
  (`DnsCreateARecord`, `DnsDeleteARecord`) expect the caller to have done it.
- **Expensive lookups are guarded.** `GitGetVmInfo` and `GitConfigInfo` are
  included with `when: ... is not defined` so the file is fetched once per play
  no matter how many roles need it.
- **`localhost` runs the API work.** Anything talking to NetBox, Zabbix, AWX,
  vCenter or Proxmox runs on the execution node, either as a `hosts: localhost`
  play or via `delegate_to: localhost`.
- **Two Python helpers run on the control node.** `Subnet.py`, `PortID.py`,
  `Ports.py` and `WWN.py` are dispatched with `script:`, `delegate_to: localhost`
  and an explicit `executable: /usr/bin/python`.
- **`validate_certs` is off** on the NetBox, AWX, vCenter, Proxmox and Vault
  calls throughout.

Collections used
----------------

No `requirements.yml` is checked in; these are expected to be present in the AWX
execution environment.

`awx.awx`, `community.hashi_vault`, `community.general`, `community.windows`,
`ansible.windows`, `chocolatey.chocolatey`, `community.vmware`,
`community.proxmox`, `netbox.netbox`, `ansible.posix`,
`dellemc.openmanage`

Plus, on the execution node: `hvac`, `pynetbox`, `pyvmomi`, `pywinrm`,
`sshpass` (for `AddToPrometheus`), `omsdk` (installed by the iDRAC playbooks
themselves), and `python` at `/usr/bin/python` for the helper scripts.

License
-------

MIT
