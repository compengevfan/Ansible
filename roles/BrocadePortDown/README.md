BrocadePortDown
===============

Persistently disables the switch port a server is connected to, and renames the
port to a plain `port<n>` (or `slot<s> port<p>`) form so it no longer looks
allocated. The inverse of `BrocadePortUp`.

What it does
------------

1. `portname | grep <ServerName>` to find the port by its name.
2. Fails if the server is not found on the switch.
3. Fails if the `portname` line splits into more than 3 fields, which is how a
   second connection shows up — the automation only supports one connection per
   switch.
4. Runs `files/PortID.py` on `localhost`, which strips the `port` prefix off the
   existing name and produces both the port identifier and the new name. A `/` in
   the identifier becomes `slot<s> port<p>`.
5. `portcfgpersistentdisable <port>`.
6. `portname <port> -n <newname>`.

Requirements
------------

- SSH access to the switch with a FOS account allowed to run
  `portcfgpersistentdisable` and `portname`.
- `/usr/bin/python` on the control node — `PortID.py` is dispatched with
  `delegate_to: localhost`.
- The port must already follow the `port<n>_<name>_<hba>` naming convention that
  `BrocadePortUp` applies; `PortID.py` splits on `_` and takes field 0.
- The target is the switch itself, so the play runs with `gather_facts: False`.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Matched against `portname` output |

`defaults/main.yml` is empty; `vars/main.yml` defines only the parsed
`ServerInfo` / `Split1`.

Note on the not-found check
---------------------------

The first task is guarded with `when: ServerName is defined` while the check
immediately after reads `SWInfo.rc`. If `ServerName` is somehow undefined the
first task is skipped and the check fails on an undefined register instead of
producing the intended message. The `fail` messages are prefixed with `Order 66`,
the marker the calling automation uses for operator-actionable failures.

Dependencies
------------

None.

Example Playbook
----------------

`BrocadePortDown.yml` in the repository root:

    ansible-playbook BrocadePortDown.yml -e target_hostname=switch01 -e ServerName=jaxsql01

License
-------

MIT
