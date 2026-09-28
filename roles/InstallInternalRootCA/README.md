InstallInternalRootCA
=====================

Makes an AlmaLinux host trust the internal root CA, `evorigin-JAX-CERT001-CA`,
system-wide. Anything that uses the system trust store - OpenSSL, curl, git,
dnf, the Vault CLI and other Go binaries - then accepts certificates issued by
the lab CA with no `VAULT_CACERT`, `-tls-skip-verify` or per-tool CA flag.

`ConfigureLinux` runs this as its first step. `InstallInternalRootCA.yml` runs
it on its own, which is the way to add the CA to a server that is already in
service: **nothing restarts and nothing reboots.**

What it does
------------

1. Checks that `GetVaultCreds` supplied the certificate and that it is PEM text.
2. Writes the certificate from Vault to
   `/etc/pki/ca-trust/source/anchors/ca.crt`.
3. Rebuilds the trust store with `update-ca-trust extract`, only when the file
   actually changed.
4. Runs `openssl verify` against the rebuilt system bundle, so a run that
   reports success means the CA really is trusted, not just that a file landed.

Re-running it changes nothing and still performs the check.

Where the certificate comes from
--------------------------------

HashiCorp Vault, never this repository. The calling playbook runs
`GetVaultCreds` with `cacert` in `includecred`, which reads
`HomeLabSecrets/data/ca_cert` and sets `cacert_info`. This role writes
`cacert_info['ca.crt']` to the host.

The secret must hold the PEM text, `-----BEGIN CERTIFICATE-----` line included.
Surrounding whitespace does not matter: the value is trimmed and written with a
single trailing newline, so re-runs compare equal whatever way it was pasted in.

`evorigin-JAX-CERT001-CA` is a single-tier root: it is self-signed, and it signs
server certificates directly (Gitea's, for example). Its thumbprint is
`C5A5656FF6942320CCDB5D45161527964DA1E967`, valid to 2052-09-21. Only the root
belongs in the anchors. An intermediate CA goes in the chain the server
presents instead.

To rotate the CA, replace the value in Vault and re-run. The file name stays
`ca.crt`, so the old root is overwritten rather than left behind as a second
anchor.

Already-running services
------------------------

The trust store changes on disk immediately, and every new process sees it. A
long-running service that read the bundle at startup keeps the old copy until
it is restarted. Nothing in this role restarts anything, so restart a service
yourself if it needs to trust the CA now.

Role Variables
--------------

| Variable | Default | Notes |
|---|---|---|
| `internal_ca_cert_file` | `ca.crt` | File name in the anchors folder |
| `cacert_info` | set by `GetVaultCreds` | Required. The certificate is read from its `ca.crt` key |

The anchors folder and bundle paths are in `vars/main.yml`.

Check mode
----------

`--check` reports whether the file would change. The verify step still runs
when the CA is already in place. It is skipped when the file would be new,
because there is nothing on the host yet to verify.

Requirements
------------

- `GetVaultCreds` run first with `cacert` in `includecred`, and Vault
  reachable from wherever the playbook runs.
- `openssl` and `ca-certificates` on the target. Both are on an AlmaLinux 9
  base install.
- SSH as root. Like `ConfigureLinux`, the tasks do not use `become`.
  `InstallInternalRootCA.yml` connects with the `linuxroot` credential from
  Vault.

Dependencies
------------

`GetVaultCreds`, called by the playbook rather than declared here, like every
other role in this repository. `InstallInternalRootCA.yml` asks it for
`linuxroot` and `cacert`, and `ConfigureLinux.yml` adds `cacert` to its list.

Example Playbook
----------------

`InstallInternalRootCA.yml` in the repository root. It defaults to the
`AlmaLinux` group, so give it a host to do one server:

    ansible-playbook InstallInternalRootCA.yml -e target_hostname=jax-vlt001.evorigin.com

Leave `target_hostname` off to do the whole group.

License
-------

MIT
