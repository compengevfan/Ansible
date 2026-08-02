BrocadeCopyFEPorts
==================

Reads the array front-end ports out of a server's existing zones on a Brocade FC
switch, so a second server can be zoned to the same ports. It is the lookup step
that feeds `Port1` and `Port2` into `BrocadeZoning`.

What it does
------------

1. `zoneshow *<ServerName>*<ArrayName>*` on the switch.
2. Fails if the output says the zone does not exist.
3. Fails if the output is not exactly 5 lines — that is what two zones look like,
   and the automation only supports two zones per switch.
4. Runs `files/Ports.py` on `localhost`, which takes the fifth underscore-
   separated field out of each of the two zone names.
5. Prints `Port1;Port2` with `debug`.

The result is **only printed**, not stored anywhere durable. `Port1` and `Port2`
are defined in `vars/main.yml` from `PortReturn.stdout_lines`, so they are usable
by later tasks within the same play, but the playbook's own output is what the
calling automation scrapes.

Requirements
------------

- SSH access to the switch with an account allowed to run `zoneshow`.
- `/usr/bin/python` on the control node — `Ports.py` is dispatched with
  `delegate_to: localhost`.
- The zone names must follow the `z_<name>_<hba>_<array>_<port>` convention that
  `BrocadeZoning` creates; `Ports.py` indexes field 4 blindly.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Server whose existing zones are read |
| `ArrayName` | yes | Array to match in the zone name |

`defaults/main.yml` is empty; `vars/main.yml` holds only the two derived port
values.

Failure messages
----------------

The `fail` messages are prefixed with `Order 66` and reference a `DASDMGT` team,
which is how the calling automation recognises an operator-actionable failure.

Dependencies
------------

None. Its output is intended for `BrocadeZoning`.

Example Playbook
----------------

`BrocadeCopyFEPorts.yml` in the repository root:

    ansible-playbook BrocadeCopyFEPorts.yml \
      -e target_hostname=switch01 -e ServerName=jaxsql01 -e ArrayName=vmax01

License
-------

MIT
