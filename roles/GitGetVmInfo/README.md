GitGetVmInfo
============

Downloads a VM's build definition from the `compengevfan/vmbuildfiles` GitHub
repository and parses it into the `VmFileContents_JSON` fact. This is where the
per-server build spec (CPU, RAM, datastore, OU, OS, network name) comes from for
every build and decom role in this repository.

The file is fetched from:

    https://raw.githubusercontent.com/compengevfan/vmbuildfiles/main/V2/<SERVERNAME>.json

`ServerName` is upper-cased first (also exposed as the `ServerNameUpper` fact),
so the JSON files in that repository are expected to be named in upper case. The
download lands in `/tmp/<ServerName>.json` on the host running the role, using
the name as passed in rather than the upper-cased form.

Callers guard the include with `when: VmFileContents_JSON is not defined` so the
file is only fetched once per play.

Requirements
------------

- Network access to `raw.githubusercontent.com` from the host running the role
  (usually the AWX execution node via `hosts: localhost`).
- A writable `/tmp`, which means this role does not work when targeted at a
  Windows host.
- The repository is public — no credential is used.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `ServerName` | yes | Short server name; case-insensitive, upper-cased internally |

Facts set:

| Fact | Contents |
|---|---|
| `ServerNameUpper` | `ServerName \| upper` |
| `VmFileContents_JSON` | The parsed build file |

Keys read from `VmFileContents_JSON` elsewhere in this repository, all under
`.VMInfo`: `OperatingSystem`, `Network`, `vCPUs`, `RAM`, `Datastore`, `OU`,
`IPAddress`.

`.VMInfo.Network` is the name of the network config consumed by `GitConfigInfo`,
which is how the two roles chain together.

Notes on behaviour
------------------

- `get_url` will not re-download an unchanged file, but it also does not fail
  loudly in a helpful way if the server name has no build file — expect a 404
  from `get_url` rather than a message naming the server.
- Nothing cleans up `/tmp/<ServerName>.json`.

Dependencies
------------

None. Typically included by `NetboxAddVM`, `ProxmoxBuildVM`, `VMwareBuildVM`,
`DnsDeleteARecord`, `AwxAddHostToInventory` and `AwxRemoveHostFromInventory`.

Example Playbook
----------------

See `GitGetVmInfo.yml` in the repository root:

    ansible-playbook GitGetVmInfo.yml -e ServerName=jax-web001

License
-------

MIT
