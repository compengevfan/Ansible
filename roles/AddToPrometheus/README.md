AddToPrometheus
===============

Adds the target host to the Prometheus scrape list on `jax-dash001l`, the
counterpart to `AddToZabbix`. Intended to be included at the end of
`ConfigureLinux.yml`, `ConfigureWindows.yml` and `ConfigureMonitoringWindows.yml`,
all of which already install an exporter (`node_exporter` on 9100,
`windows_exporter` on 9182) but previously had no way to tell Prometheus about it.

How it works
------------

The role writes one small **per-host target file** into a directory that
Prometheus watches via `file_sd_configs`:

    /opt/prometheus/config/targets/windows/dc01.evorigin.com.yml

    # Managed by the Ansible role AddToPrometheus. Do not edit by hand.
    - targets: ['dc01.evorigin.com:9182']
      labels:
        instance: dc01.evorigin.com

It does **not** edit `prometheus.yml`, and nothing is reloaded or restarted —
file-based discovery is re-read at runtime.

One file per host, rather than appending to a shared list, is the whole point:
Ansible runs hosts in parallel, and concurrent read-modify-write of a single
`prometheus.yml` silently drops targets with no error. Separate files cannot
collide, and identical content on a re-run means `changed=0`.

Removing a host from monitoring is just deleting its file.

One-time bootstrap (required)
-----------------------------

**The role will fail with a clear message until this is done.** Historically only
`prometheus.yml` itself was bind-mounted into the container, so a new `targets/`
directory on the host is not visible to Prometheus without a mount change.

On `jax-dash001l`:

1. Create the directories:

       mkdir -p /opt/prometheus/config/targets/{linux,windows}

2. Add a mount to the Prometheus compose file, alongside the existing
   `prometheus.yml` one:

       - /opt/prometheus/config/targets:/etc/prometheus/targets:ro

3. Add two jobs to `/opt/prometheus/config/prometheus.yml`. Note these are the
   **container's** paths, not the host's:

       - job_name: 'node_exporter'
         file_sd_configs:
           - files: ['/etc/prometheus/targets/linux/*.yml']
             refresh_interval: 30s

       - job_name: 'windows_exporter'
         file_sd_configs:
           - files: ['/etc/prometheus/targets/windows/*.yml']
             refresh_interval: 30s

4. Recreate the container. A mount change needs a recreate, not a reload:

       docker compose up -d

5. Confirm:

       docker inspect <container> --format '{{json .Mounts}}'
       docker exec <container> ls /etc/prometheus/targets
       curl -s http://jax-dash001l:9090/api/v1/status/config | grep -c file_sd

Requirements
------------

- The calling play must fetch the **`linuxroot`** credential via `GetVaultCreds`
  — the role authenticates to `jax-dash001l` with it.
- `sshpass` in the execution environment, since that credential is a password.
- The control node must be able to reach `jax-dash001l` on 9090 (API) and 22.
- Target hosts must resolve in DNS from inside the Prometheus container, since
  targets are written as FQDNs rather than IP addresses.

Role Variables
--------------

See `defaults/main.yml`.

| Variable | Default | Notes |
|---|---|---|
| `prometheus_host` | `jax-dash001l` | Where the target files are written |
| `prometheus_api_url` | `http://jax-dash001l:9090` | Used for the preflight and verify checks |
| `prometheus_targets_dir` | `/opt/prometheus/config/targets` | **Host** path, not the container path |
| `prometheus_os_map` | Win32NT / Linux | `ansible_system` → job, port, subdirectory |
| `prometheus_verify_target` | `true` | Poll the API until the target is discovered |
| `prometheus_verify_retries` / `_delay` | `10` / `6` | Up to ~60s, covering the 30s `refresh_interval` |

Checks
------

The role brackets the write with two checks, because both failure modes are
otherwise completely silent:

- **Preflight** — reads the running config from the API and fails if no job for
  this OS uses `file_sd_configs`, i.e. the bootstrap above was never done.
- **Verify** — after writing, polls `/api/v1/targets` until the host appears,
  and fails pointing at the bind mount if it never does. This asserts the target
  was *discovered*, not that it is `up`; health also depends on the exporter and
  the host firewall, which are a different problem with a different fix.

Set `prometheus_verify_target: false` to skip the poll if the added runtime
matters more than the check.

License
-------

MIT
