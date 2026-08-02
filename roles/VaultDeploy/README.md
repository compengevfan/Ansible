VaultDeploy
===========

Installs HashiCorp Vault on a RHEL-family host from the official HashiCorp repo,
writes a raft-storage config with TLS, and starts the service.

This is the role that stands up the Vault every other role in this repository
reads its credentials from, so it is the one thing here that cannot depend on
`GetVaultCreds`.

What it does
------------

1. Opens 8200/tcp and 8201/tcp in the `public` firewalld zone, permanently, then
   reloads firewalld with a shell command.
2. Installs `yum-utils` and adds the HashiCorp RHEL repo.
3. Installs `vault-1.15.6` (pinned).
4. Creates `/var/lib/vault/data` owned by `vault:vault`.
5. Renders `templates/config.hcl.j2` to `/etc/vault.d/vault.hcl`.
6. Appends `export VAULT_ADDR="https://$(hostname):8200"` to `/etc/profile` and
   `/etc/bashrc`.
7. Restarts and enables the `vault` service.

The config it writes
--------------------

    storage "raft"     -> /var/lib/vault/data, node_id = ansible_hostname
    listener "tcp"     -> 0.0.0.0:8200, TLS enabled
    disable_mlock      = true
    api_addr           = https://vault.evorigin.com:8200
    cluster_addr       = https://vault.evorigin.com:8201
    ui                 = true

Certificates are **not** managed by this role. The listener expects to find them
already at:

    /app/certs/<hostname>-certificate-export-with-private-key-public.crt
    /app/certs/<hostname>-certificate-export-with-private-key-decrypted.key

Put them there before running it, or the service fails to start.
`CreateMsCaCertificate` is what produces that `.crt` / `.key` pair.

Requirements
------------

- A RHEL-family host with `firewalld` and `dnf`/`yum`. The `ansible.posix`
  collection for the firewalld module.
- Root, or an account that can act as root — the tasks do not use `become`.
- Outbound HTTPS to `rpm.releases.hashicorp.com`.
- TLS certificate and key already in place, as above.

Role Variables
--------------

None. `defaults/main.yml` and `vars/main.yml` are empty, and the template reads
only `ansible_hostname`, so the play must gather facts. The Vault version, data
path, ports, certificate paths and cluster addresses are all fixed — the version
in `tasks/main.yml` and the rest in `templates/config.hcl.j2`.

Notes on behaviour
------------------

- Vault is **not initialised or unsealed** by this role. After it runs, do
  `vault operator init` and unseal by hand.
- The role is not fully idempotent: `yum-config-manager --add-repo` and the
  firewalld reload are shell commands that report changed every run, and the
  service task uses `state: restarted`, so every run bounces Vault.
- The `.crt` and `.key` paths in the template contain stray quotes around the
  interpolated hostname (`/app/certs/"{{ ansible_hostname }}"-...`), which end up
  literally in the rendered file. If the service will not start, check the
  rendered `/etc/vault.d/vault.hcl` first.
- `handlers/main.yml` defines a `vault_restart` handler that nothing notifies.

Dependencies
------------

None.

Example Playbook
----------------

`VaultDeploy.yml` in the repository root:

    ansible-playbook VaultDeploy.yml --limit vault01.evorigin.com

License
-------

MIT
