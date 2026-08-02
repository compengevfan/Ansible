CreateMsCaCertificate
=====================

Requests a certificate from the Microsoft enterprise CA using `certreq`, installs
it into the local machine store, and exports it three ways — `.pfx`, `.key` and
`.crt` — so it can be used by non-Windows services as well.

Everything runs on the CA-joined Windows host itself.
`CreateMsCaCertificate.yml` targets `jax-cert001.evorigin.com`.

What it does, in order
----------------------

1. Deletes and recreates `cert_folder`, so a re-run starts clean.
2. Renders `templates/request.inf.j2` to `<cert_folder>\<ServerName>.inf`.
3. `certreq -new` to produce the CSR.
4. `certreq -submit -config "<ca_config>"` to get the signed `.cer`.
5. `certreq -accept` to install it into `Cert:\LocalMachine\My`.
6. Finds the thumbprint by matching the subject CN, and prints it with `debug`.
7. `Export-PfxCertificate` to `<cert_folder>\<ServerName>.pfx`.
8. `openssl pkcs12` twice, splitting the PFX into `.key` and `.crt`.

Wildcard vs. host certificates
------------------------------

`Wildcard` controls both the subject and the SAN:

| `Wildcard` | CN and SAN |
|---|---|
| `false` (default) | `<ServerName>.evorigin.com` |
| `true` | `*.<ServerName>` — here `ServerName` is the **domain**, not a host |

The playbook mirrors this in `cert_folder`, which becomes
`C:\CertStuff\wildcard.<ServerName>` for a wildcard request.

Requirements
------------

- WinRM to a domain-joined Windows host that can reach the CA, with an account
  allowed to enrol against `cert_template`.
- `openssl.exe` on `PATH` on that host — the last two tasks shell out to it. It
  is not installed by this role.
- The template must permit an exportable private key; `request.inf.j2` sets
  `Exportable = TRUE`, but the CA template has the final say.
- `certificateauthority_info` from Vault, which supplies `ca_config` and
  `cert_template`. The playbook fetches it on `localhost` and reads it back
  through `hostvars`.

Role Variables
--------------

| Variable | Default | Notes |
|---|---|---|
| `Wildcard` | `false` | See above. Only `defaults/main.yml` entry |
| `ServerName` | — | Required. Host short name, or the domain when `Wildcard` is true |
| `KeyLength` | — | Required. Consumed by the template; no default is set |
| `cert_folder` | — | Required. Where everything is written |
| `ca_config` | — | Required. `<CA host>\<CA name>` for `certreq -submit` |
| `cert_template` | — | Required. CA template name |
| `pfx_password` | — | Required. See below |

The subject beyond the CN is fixed in the template:
`O=EvOrigin, OU=Lab, L=Jax, ST=FL, C=US`.

The PFX password
----------------

`CreateMsCaCertificate.yml` sets `pfx_password: "DeleteMe"`, commented as *"not
really used but it is required by the CA"*. It is a real password on a real
export: the `.pfx` and the decrypted `.key` are both left on disk in
`cert_folder` protected by it. Retrieve and remove them promptly.

Notes on behaviour
------------------

- The role is **not idempotent** by design — the first task deletes
  `cert_folder`, so every run issues a new certificate.
- The thumbprint lookup takes `Select-Object -Last 1` on a subject match, so an
  older certificate with the same CN in the store does not break it, but nothing
  verifies the one selected is the one just issued.
- There is no `handlers/`, `meta/`, `vars/` or `tests/` directory in this role.

Dependencies
------------

None as an Ansible dependency. The playbook pairs it with `GetVaultCreds`
(`certificateauthority`).

Example Playbook
----------------

`CreateMsCaCertificate.yml` in the repository root:

    ansible-playbook CreateMsCaCertificate.yml \
      -e ServerName=jax-web001 -e KeyLength=2048 -e Wildcard=false

License
-------

MIT
