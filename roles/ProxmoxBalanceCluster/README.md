ProxmoxBalanceCluster
=====================

> **Not implemented.** This role is an empty scaffold. It currently contains only
> empty `files/` and `templates/` directories — there is no `tasks/main.yml`, so
> including it does nothing. Nothing in this repository references it.
>
> This README describes what the role is *for* and the conventions an
> implementation should follow. It does not describe behaviour that exists.

Intent
------

Rebalance running VMs across the Proxmox cluster nodes — migrating guests off
over-committed nodes so CPU and memory allocation is spread more evenly. Proxmox
has no built-in DRS equivalent, which is the gap this role is meant to fill.

Where it would fit
------------------

The other two Proxmox roles here act on a single VM by name:

| Role | Scope |
|---|---|
| `ProxmoxBuildVM` | Clone, size and start one VM |
| `ProxmoxRemoveVM` | Stop and delete one VM |
| `ProxmoxBalanceCluster` | The cluster as a whole |

That difference matters for the implementation: the existing roles are handed a
`ServerName` and read everything else out of NetBox, whereas balancing has to
enumerate the cluster's current state from Proxmox itself.

Conventions an implementation should follow
-------------------------------------------

These are established by the sibling roles, not by any code in this one:

- **Credentials come from Vault.** Include `GetVaultCreds` with
  `includecred: [proxmoxroot]` and use `proxmoxroot_cred.username` /
  `.password`. Do not add a new credential path without adding it to
  `GetVaultCreds` first.
- **Run on the execution node.** Both existing Proxmox roles are driven from
  `hosts: localhost`; the Proxmox API is reached over the network, not by
  connecting to a node.
- **`api_host` is currently hard-coded** to `pmx1.evorigin.com` in both sibling
  roles, with `node: pmx1`. A balancing role needs to address every node, so this
  is the one convention worth breaking — put the node list or a cluster endpoint
  in `defaults/main.yml` rather than inline.
- **`validate_certs: no`** is used throughout this repository's Proxmox and
  NetBox calls.

Things worth deciding before writing it
---------------------------------------

- **Live migration vs. cold.** Live migration needs shared storage; the build
  role clones to a per-VM datastore taken from NetBox's `Datastore` custom
  field, so whether every guest can actually be migrated live is not a given.
- **What "balanced" means.** Allocated vCPU/RAM is easy to read and easy to
  reason about; actual utilisation is more useful and more work. Pick one and
  state it in this README.
- **Dry run.** A role that moves running guests around should support
  `--check`, or a `*_apply: false` default, so the intended moves can be
  reviewed before anything migrates.
- **Whether NetBox needs updating.** `NetboxAddVM` records a cluster on the VM
  object. If migrations should be reflected there, that is an extra step; if not,
  the NetBox cluster field will drift.

Requirements
------------

Once implemented: the `community.proxmox` collection, the `proxmoxroot`
credential in Vault, and API reachability to the cluster from the AWX execution
node.

Role Variables
--------------

None yet — `defaults/main.yml` does not exist.

Dependencies
------------

None yet. Expected: `GetVaultCreds`.

Example Playbook
----------------

There is no playbook for this role, and it should not be wired into one until it
has tasks.

License
-------

MIT
