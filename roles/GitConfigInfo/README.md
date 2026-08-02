GitConfigInfo
=============

The network-config counterpart to `GitGetVmInfo`. Downloads a named network
configuration from the `compengevfan/vmbuildfiles` GitHub repository and parses
it into the `ConfigFileContents_JSON` fact.

The file is fetched from:

    https://raw.githubusercontent.com/compengevfan/vmbuildfiles/main/V2/ConfigInfo/<CONFIG>.json

`Config` is upper-cased for the URL (also exposed as the `ConfigUpper` fact) and
saved to `/tmp/<Config>.json` under the name as passed in.

In practice the value passed for `Config` is `VmFileContents_JSON.VMInfo.Network`
from `GitGetVmInfo`, so a server's build file names its network and this role
resolves that name into addressing:

    - name: Get Config Info
      include_role:
        name: GitConfigInfo
      vars:
        Config: "{{ VmFileContents_JSON.VMInfo.Network }}"
      when: ConfigFileContents_JSON is not defined

Requirements
------------

- Network access to `raw.githubusercontent.com` from the host running the role.
- A writable `/tmp`, so this role does not work when targeted at a Windows host.
- The repository is public — no credential is used.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `Config` | yes | Network config name; case-insensitive, upper-cased internally |

Facts set:

| Fact | Contents |
|---|---|
| `ConfigUpper` | `Config \| upper` |
| `ConfigFileContents_JSON` | The parsed config file |

Keys read from `ConfigFileContents_JSON` elsewhere in this repository: `Domain`,
`Subnet`, `Gateway`, `DNS1`, `DNS2`, `Cluster`, `PortGroup`.

Dependencies
------------

None, but it is only useful after `GitGetVmInfo` unless the caller supplies
`Config` directly. Included by `NetboxAddVM`, `ProxmoxBuildVM`, `VMwareBuildVM`
and `DnsDeleteARecord`.

Example Playbook
----------------

No dedicated playbook exists; the role is always included by another. To exercise
it directly:

    - hosts: localhost
      connection: local
      tasks:
        - include_role:
            name: GitConfigInfo
          vars:
            Config: vlan10
        - debug:
            var: ConfigFileContents_JSON

License
-------

MIT
