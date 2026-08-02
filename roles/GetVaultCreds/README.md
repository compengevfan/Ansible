GetVaultCreds
=============

Pulls credentials out of HashiCorp Vault and sets them as facts, so no other role
in this repository has to know where a secret lives. Nearly every playbook here
starts with it.

The caller passes a list of credential names in `includecred`, and the role sets
one fact per requested name. Anything not listed is skipped, so asking for one
credential does not read the rest.

    - name: Obtain Credentials
      include_role:
        name: GetVaultCreds
      vars:
        includecred:
          - evoriginda
          - zabbixapi

Available credentials
---------------------

Each entry is looked up with `community.hashi_vault.hashi_vault` and
`validate_certs=False`. The fact name is what other roles reference.

| `includecred` value | Fact set | Vault path (under `HomeLabSecrets/data/`) |
|---|---|---|
| `idrac` | `idrac_cred` | `dell/iDRAC` |
| `netbox` | `netbox_cred` | `netbox` |
| `git` | `git_cred` | `git` |
| `vcenter` | `vcenter_cred` | `vmware/vcenter` |
| `windowslocaladmin` | `windowslocaladmin_cred` | `windowslocaladmin` |
| `evorigindns` | `evorigindns_cred` | `serviceaccounts/evorigin/svcdns` |
| `evoriginda` | `evoriginda_cred` | `serviceaccounts/evorigin/da` |
| `linuxroot` | `linuxroot_cred` | `linuxroot` |
| `proxmoxroot` | `proxmoxroot_cred` | `proxmox/root` |
| `certificateauthority` | `certificateauthority_info` | `certificateauthority` |
| `awx` | `awx_cred` | `awx` |
| `test` | `test_cred` | `test` |
| `zabbixapi` | `zabbixapi_cred` | `zabbix` |

The facts are dictionaries whose keys come from the secret itself — usually
`username` and `password`, but not always. Callers in this repository also use:

- `netbox_cred.url`, `netbox_cred.token`, `netbox_cred.api_token`
- `evorigindns_cred.dnsservername`
- `vcenter_cred.servername`
- `zabbixapi_cred.token`
- `certificateauthority_info.ca_config`, `.cert_template` — CA configuration
  rather than a credential at all

Requirements
------------

- The `community.hashi_vault` collection, plus `hvac` in the execution
  environment.
- Vault addressing and authentication come from the environment (`VAULT_ADDR`,
  `VAULT_TOKEN`, or the credential AWX injects into the job) — the role does not
  set them.

Role Variables
--------------

| Variable | Required | Notes |
|---|---|---|
| `includecred` | yes | List of credential names from the table above |

`defaults/main.yml` and `vars/main.yml` are empty. An `includecred` value that
is not in the table is silently ignored — every task is gated on an `in`
condition, so a typo produces no error, just a missing fact later.

Notes on behaviour
------------------

- **The facts land on whichever host the including play targets.** A later task
  using `delegate_to` will re-template `ansible_user` / `ansible_password` for
  the delegate, which never had the fact — see `AddToZabbix` for how that is
  worked around.
- When a play needs a credential on `localhost` while running against remote
  hosts, the pattern used here is a separate `hosts: localhost` play followed by
  a `hostvars['localhost']` lookup (see `CreateMsCaCertificate.yml`).
- Most lookups set `no_log: true`. The `awx` and `test` lookups currently do not.

Dependencies
------------

None.

Example Playbook
----------------

See `GetVaultCreds.yml` in the repository root, which fetches `idrac` and
`netbox` on `localhost`.

License
-------

MIT
