BrocadeZoning
=============

Zones a server into a storage array on a Brocade FC switch. Given a server name
and an array with two front-end ports, it finds the server's switch port, reads
the WWN off it, creates an alias, creates two zones (one per array port), adds
them to the active config and enables it.

This is the oldest group of roles in the repository and it talks to the switch
over `raw` SSH rather than through a module, because Brocade FOS gives you a
restricted shell and not much else.

What it does, in order
----------------------

1. `portname | grep <ServerName>` to locate the server's port.
2. Fails if the server is not found, or if more than one connection is found —
   the automation only supports a single connection per switch.
3. `portshow <port>` and fails if the port is OFFLINE.
4. Runs `files/WWN.py` on `localhost` to pull the WWN out of the `portshow`
   output (it returns the line containing `u\t`).
5. `alicreate <alias>,"<wwn>"`.
6. `zonecreate` twice, once per array port.
7. `cfgsave -f`.
8. `configshow | grep enable:` to find the active config name.
9. `cfgadd` both zones and `cfgenable <cfg> -f`.

Naming
------

The port name on the switch is expected to look like `port<n>_<name>_<hba>`, and
everything is derived from it:

| Value | Derived as |
|---|---|
| `PortNumber` | The `port<n>` prefix with `port` stripped |
| `AliasName` | The second and third underscore-separated fields joined |
| `Zone1Name` | `z_<AliasName>_<Array>_<Port1>` |
| `Zone2Name` | `z_<AliasName>_<Array>_<Port2>` |

If the switch ports have not been renamed to that convention, the role fails or
produces nonsense names. `BrocadePortUp` is what applies the convention.

Requirements
------------

- SSH access to the switch with a FOS account allowed to run `alicreate`,
  `zonecreate`, `cfgadd`, `cfgenable` and `cfgsave`.
- `/usr/bin/python` on the control node — `WWN.py` is dispatched with
  `delegate_to: localhost` and an explicit `executable`.
- The target is the switch itself, so plays run with `gather_facts: False`.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Matched against `portname` output |
| `Array` | yes | Array name; forms part of the zone and member names |
| `Port1`, `Port2` | yes | The two array front-end ports; `BrocadeCopyFEPorts` produces these |

`defaults/main.yml` is empty. `vars/main.yml` holds only derived values (the
name parsing above), not settings.

Failure messages
----------------

The `fail` messages are prefixed with `Order 66` and reference a `DASDMGT` team.
That prefix is how the calling automation recognises an operator-actionable
failure; it is not an Ansible convention.

Dependencies
------------

None as an Ansible dependency, but `Port1` and `Port2` normally come from
`BrocadeCopyFEPorts`.

Example Playbook
----------------

`BrocadeZoning.yml` in the repository root:

    ansible-playbook BrocadeZoning.yml \
      -e target_hostname=switch01 \
      -e ServerName=jaxsql01 -e Array=vmax01 -e Port1=1a -e Port2=2a

License
-------

MIT
