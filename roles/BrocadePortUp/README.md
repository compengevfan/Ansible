BrocadePortUp
=============

Persistently enables a port on a Brocade FC switch and renames it to the
convention the rest of the Brocade roles depend on.

What it does
------------

1. Runs `files/PortID.py` on `localhost` to turn `PortNumber` and `SlotNumber`
   into a port identifier. On a non-bladed switch pass `SlotNumber: -1` and the
   port number is used as-is; otherwise the result is `<slot>/<port>`.
2. `portshow <port>`.
3. Fails if line 6 of that output reads `portDisableReason: None`, i.e. the port
   is already enabled.
4. `portcfgpersistentenable <port>`.
5. `portname <port> -n port<port>_<ServerName>_<HBAPort>`.

That name format is what `BrocadeZoning` and `BrocadePortDown` parse, so the
rename is not cosmetic — skipping it breaks the later roles.

Requirements
------------

- SSH access to the switch with a FOS account allowed to run
  `portcfgpersistentenable` and `portname`.
- `/usr/bin/python` on the control node — `PortID.py` is dispatched with
  `delegate_to: localhost`.
- The target is the switch itself, so the play runs with `gather_facts: False`.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `PortNumber` | yes | Port number on the switch |
| `SlotNumber` | yes | Blade slot, or `-1` for a non-bladed switch |
| `ServerName` | yes | Used in the new port name |
| `HBAPort` | yes | HBA port identifier, used in the new port name |

`defaults/main.yml` is empty; `vars/main.yml` defines only the derived `Name`.

Note on the already-enabled check
---------------------------------

The check indexes `PortInfo.stdout_lines[5]` by position rather than searching
for the field. A FOS version whose `portshow` output is laid out differently will
either fail on a port that is fine, or enable one it should have refused. The
`fail` message is prefixed with `Order 66`, the marker the calling automation
uses for operator-actionable failures.

Dependencies
------------

None.

Example Playbook
----------------

`BrocadePortUp.yml` in the repository root:

    ansible-playbook BrocadePortUp.yml \
      -e target_hostname=switch01 -e PortNumber=12 -e SlotNumber=-1 \
      -e ServerName=jaxsql01 -e HBAPort=hba0

License
-------

MIT
