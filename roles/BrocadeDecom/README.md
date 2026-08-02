BrocadeDecom
============

Removes a server's zoning from a Brocade FC switch: both of its zones come out of
the active config, the zones themselves are deleted, and its alias is deleted.
The inverse of `BrocadeZoning`.

What it does, in order
----------------------

1. `configshow | grep enable:` to find the active config name.
2. `zoneshow --ic "z_<ServerName>*" | grep zone` to find the server's two zones.
3. `cfgremove <cfg>, "<zone1>;<zone2>"`.
4. `cfgenable <cfg> -f`.
5. `zonedelete` on each zone.
6. `cfgsave -f`.
7. `alishow | grep 'alias:[[:space:]]<ServerName>'` to find the alias.
8. `alidelete <alias>` and `cfgsave -f` again.

Exactly two zones are assumed
-----------------------------

`vars/main.yml` reads `ZoneResponse.stdout_lines[0]` and `[1]` unconditionally.
Unlike `BrocadeCopyFEPorts` there is **no guard** on the zone count, so a server
with one zone, or with more than two, produces a templating error or removes only
the first two. Check `zoneshow --ic "z_<ServerName>*"` before running it against
anything unusual.

Note also that this role changes the switch in steps: `cfgenable` runs before the
zones are deleted, and `cfgsave` runs twice. An interrupted run can leave the
switch part-way through — zones removed from the config but still defined, or the
alias still present.

Requirements
------------

- SSH access to the switch with a FOS account allowed to run `cfgremove`,
  `cfgenable`, `zonedelete`, `alidelete` and `cfgsave`.
- The target is the switch itself, so the play runs with `gather_facts: False`.
- No Python script is used by this role, so nothing is delegated to the control
  node.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Matched against the `z_<ServerName>*` zone names and the alias name |

`defaults/main.yml` is empty. `vars/main.yml` holds only values derived from
command output (`CfgName`, `Zone1Name`, `Zone2Name`, `Alias`).

Dependencies
------------

None.

Example Playbook
----------------

`BrocadeDecom.yml` in the repository root:

    ansible-playbook BrocadeDecom.yml -e target_hostname=switch01 -e ServerName=jaxsql01

License
-------

MIT
