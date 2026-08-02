AwxRemoveHostFromInventory
==========================

The decommission counterpart to `AwxAddHostToInventory`. Removes a host from the
`Linux` inventory on the AWX controller `jax-k3s001.evorigin.com`.

Removing the host removes it from its groups as well, so the group tasks that
`AwxAddHostToInventory` performs have no counterpart here — they are present in
`tasks/main.yml` but commented out.

Only AlmaLinux is handled
-------------------------

As with the add role, the work is gated on:

    when: '"Alma" in VmFileContents_JSON.VMInfo.OperatingSystem'

This means the role still needs the server's build file in
`compengevfan/vmbuildfiles` to be present at decom time. If the build file has
already been deleted, `GitGetVmInfo` fails before this role gets a chance to run.

Requirements
------------

- The `awx.awx` collection in the execution environment.
- Reachability of `jax-k3s001.evorigin.com`.
- The `awx` credential in Vault, fetched by the role itself.
- `validate_certs: no` is set, so the controller's certificate is not verified.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Short server name; upper-cased into `ServerNameUpper` |
| `VmFileContents_JSON` | no | Fetched via `GitGetVmInfo` if not already defined |

`defaults/main.yml` and `vars/main.yml` are empty; the controller host and
inventory name are hard-coded in `tasks/main.yml`.

Dependencies
------------

Includes `GetVaultCreds` (for `awx`) and `GitGetVmInfo` (only when
`VmFileContents_JSON` is not already set).

Cosmetic note
-------------

The role was copied from `AwxAddHostToInventory` and the comments and task names
were not updated — `tasks/main.yml`, `defaults/main.yml` and `vars/main.yml` all
still say `AwxAddHostToInventory`, and the removal task is still named "Add
AlmaLinux Server to AWX Inventory". Only `state: absent` distinguishes it.

Example Playbook
----------------

There is no dedicated playbook for this role in the repository root. To run it:

    - hosts: localhost
      gather_facts: yes
      tasks:
        - include_role:
            name: AwxRemoveHostFromInventory
          vars:
            ServerName: jax-web001

License
-------

MIT
