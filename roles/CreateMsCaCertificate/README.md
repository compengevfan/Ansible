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
2. Renders `templates/request.inf.j2` to `<cert_folder>\<cert_name>.inf`.
3. `certreq -new` to produce the CSR.
4. `certreq -submit -config "<ca_config>"` to get the signed `.cer`.
5. `certreq -accept` to install it into `Cert:\LocalMachine\My`.
6. Reads the thumbprint from the `.cer` issued this run, and prints it with `debug`.
7. `Export-PfxCertificate` to `<cert_folder>\<cert_name>.pfx`.
8. `openssl pkcs12` twice, splitting the PFX into `.key` and `.crt`.

Wildcard vs. host certificates
------------------------------

`Wildcard` controls the subject, the SAN and the file names:

| `Wildcard` | CN | SAN | `cert_name` (files and folder) |
|---|---|---|---|
| `false` (default) | `<ServerName>.<Domain>` | same as CN | `<ServerName>` |
| `true` | `*.<Domain>` | `*.<Domain>` and `<Domain>` | `wildcard.<Domain>` |

A wildcard request needs no `ServerName`. The bare domain is added to the SAN
because `*.evorigin.com` does not match `evorigin.com` itself. A wildcard covers
one label only: `*.evorigin.com` does not match `app.lab.evorigin.com`.

The playbook sets `cert_folder` to `C:\CertStuff\<cert_name>`, so a wildcard
lands in `C:\CertStuff\wildcard.evorigin.com\wildcard.evorigin.com.pfx` (and
`.key`, `.crt`).

Requirements
------------

- WinRM to a domain-joined Windows host that can reach the CA, connecting as an
  account that is a local administrator there — the `certreq` and PFX export
  tasks use `become_method: runas` to `SYSTEM`, which needs that.
- Enrolment happens as the **computer account** (`<host>$`), not as the WinRM
  user, because SYSTEM is what goes out on the wire. `cert_template` must grant
  it Enroll, and must allow the subject to be supplied in the request — the
  subject comes from `request.inf.j2`, not from the machine's AD object.
- `openssl.exe` on the **machine** `PATH` on that host — the last two tasks
  shell out to it. It is not installed by this role.
- The template must permit an exportable private key; `request.inf.j2` sets
  `Exportable = TRUE`, but the CA template has the final say.
- `certificateauthority_info` from Vault, which supplies `ca_config` and
  `cert_template`. The playbook fetches it on `localhost` and reads it back
  through `hostvars`.

Role Variables
--------------

| Variable | Default | Notes |
|---|---|---|
| `Wildcard` | `false` | See above |
| `Domain` | `evorigin.com` | DNS domain for the CN and SAN |
| `ServerName` | — | Host short name. Required unless `Wildcard` is true (asserted) |
| `cert_name` | derived | Base name for the files; set in `defaults/main.yml` |
| `cert_cn` | derived | Subject CN; set in `defaults/main.yml` |
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
- The thumbprint comes from the `.cer` that `certreq -submit` wrote this run,
  so older certificates with the same CN in the store cannot be picked up.
- There is no `handlers/`, `meta/`, `vars/` or `tests/` directory in this role.

Dependencies
------------

None as an Ansible dependency. The playbook pairs it with `GetVaultCreds`
(`certificateauthority`).

Example Playbook
----------------

`CreateMsCaCertificate.yml` in the repository root:

    ansible-playbook CreateMsCaCertificate.yml \
      -e ServerName=jax-web001 -e KeyLength=2048

A wildcard for the domain:

    ansible-playbook CreateMsCaCertificate.yml \
      -e KeyLength=2048 -e Wildcard=true

License
-------

MIT
