# Server diagnostics

The Servers instrument opens an **on-demand** SSH monitor. There is one persistent
SSH stream per configured connection while its window is open. Closing it ends
the owned local SSH process groups, including SSH proxy descendants. It does not
install a remote agent, use sudo, restart services or modify the remote machine.
The shelf reads a private last-observation cache; it never initiates SSH itself.

Create the private file `$XDG_CONFIG_HOME/rglauncher-linux/servers.json` (normally
`~/.config/rglauncher-linux/servers.json`). A new installation has no inventory:

```json
{"hosts": [], "interval": 2}
```

Each trusted local host object requires `id`, `label` and `target`. Optional fields
are integer `port` (default22), `identity_file`, `known_hosts_file`, and `group`
(default `VPS`). Targets support standard SSH aliases and user/host destinations;
they cannot contain command options, whitespace or shell expressions. Key and
known-host paths must be absolute or start with `~`; each remains local. IDs must
be unique. Labels/group names are display text. Store actual connection identities,
keys, inventory and caches outside the source/distribution. Editing an SSH alias's
underlying profile requires reopening the monitor to reconnect to its new route.

Authentication uses the user's existing SSH setup. Diagnostics require Python3.7+
and Linux `/proc` on the remote account. Background streams use batch mode, strict
existing host-key verification, no askpass, no forwarding, no local SSH commands,
no multiplexed/daemonizing connection, and no host-key updates. Python receives
the bundled standard-library sampler through stdin with bytecode writes disabled.
The separate interactive SSH action is explicit and uses argument arrays rather
than a shell expression. Authentication, unknown/changed host keys, unsupported
shells and unreachable connections remain distinct states. Auth/key/protocol
failures stop retries until the monitor is reopened. Transient connection failures
retry after2seconds, doubling up to30seconds.

## What is measured

CPU utilization, core count, RAM, swap, load, uptime, network receive/transmit rates,
block-device read/write rates and top process names come from `/proc`. Process
arguments, environment, logs and credentials are never collected. CPU/network/IO
rates require a second observation; unavailable/first rates are `null`, not zero.
Process CPU can exceed100% when it uses multiple cores. Network rates sum observed
interfaces except loopback; bridges/virtual interfaces can count the same traffic
more than once. Block IO sums observed non-loop physical block devices, excluding
device-mapper/RAID layers to reduce double counting. These are server counters,
not a claim about hypervisor billing, physical network throughput or storage QoS.

Filesystem capacity uses bounded `df`; failed unit names/descriptions use read-only
`systemctl --failed`; Docker names/states use read-only `docker ps -a`. Each command
has a2second timeout and64KiB output limit. Up to64filesystems/failed units,
128containers/interfaces and12top processes are retained. Optional unavailable
systemd/Docker queries carry an error; an unavailable query does not mean zero
failed services or zero containers. Heavy observations refresh on a5second
monotonic cache cadence; lightweight sampling defaults to2seconds. Filesystem
queries may themselves hang until their timeout on unhealthy remote mounts.

All streams, command output, line sizes, collection counts and local shutdown waits
are bounded. Configured sampling accepts1–60seconds; intervals above8seconds will
intentionally show stale gaps because the health freshness threshold remains8s.
This is a remote observation tool; it does not certify service availability,
application request latency, customer reachability or server security.

## Backend contract

`Host` is immutable and exposes `id`, `label`, `target`, `port`, `identity_file`,
`known_hosts_file`, `group`. `load_hosts()` reads the private inventory;
`load_interval()` returns its interval. `ssh_argv(host, interactive=True)` builds
an explicit terminal connection without a sampler command. `host_transport_id`
hashes target/port/local key path/known-host path so a summary can reject metrics
from an older transport under a reused ID. It does not hash/read private key data.

`FleetMonitor(hosts, interval=2)` provides `start()`, bounded `stop()` and thread-safe
`snapshot()`. Each snapshot row contains:

```text
id, label, target, port, group, transport_id,
state, observed_at, age, stale, error, metrics
```

States are `connecting`, `online`, `stale`, `auth_required`, `host_key_error`,
`unreachable`, `unsupported`, `error`, `stopped`. The last metrics survive
disconnection and closure; their age/stale flag stays visible. `observed_at` is
local receipt time, never an assumed-correct remote clock. Active monitor ages
use local monotonic elapsed time. A stream that stops producing valid observations
becomes stale after8seconds even when no new input/error arrives. A stalled stream
is eventually closed and retried. No invalid JSON/banner can create healthy data.

Metrics schema1 groups:

| Group | Fields |
|---|---|
| `cpu` | `percent`, `cores`, `updated_at` |
| `memory` | `total_bytes`, `used_bytes`, `available_bytes`, `percent`, `updated_at` |
| `swap` | `total_bytes`, `used_bytes`, `percent`, `updated_at` |
| `load` | `one`, `five`, `fifteen`, `updated_at` |
| `network` | `rx_bytes_per_second`, `tx_bytes_per_second`, `interfaces`, `updated_at` |
| `disk` | `read_bytes_per_second`, `write_bytes_per_second`, `filesystems`, `updated_at`, `filesystems_updated_at`, optional `error` |
| `services` | `failed` list of unit/description, `updated_at`, optional `error` |
| `containers` | `items` list of id/name/state/status, `updated_at`, optional `error` |
| `processes` | list of pid/name/cpu_percent/memory_bytes |

Top-level metrics also include `sampled_at` and `uptime_seconds`. Filesystem rows
contain mount/total_bytes/used_bytes/available_bytes/percent. Group timestamps are
normalized into the local receipt clock by subtracting their remote sample-relative
age. Disk's general timestamp covers live IO; its filesystem timestamp covers the
cached filesystem list. Every field is validated/bounded; unknown process/metric
fields are dropped rather than persisted.

`publish_cache(snapshot)` atomically writes mode0600
`$XDG_STATE_HOME/rglauncher-linux/fleet-cache.json`. It includes publisher PID and
process starttime, without process arguments or environment. `load_cache()` performs
no SSH and returns rows with recalculated age and `cache_active`. Dead/reused
publisher identity makes old online rows stale immediately, including after a
window crash. Future wall timestamps are stale rather than indefinitely fresh.
The UI publishes a stopped snapshot on graceful closure. Consumers must match ID
and current transport identity before presenting a cached row as current data.

## Verification

`python3 -B -m unittest discover -s tests -p test_fleet.py -v` uses fake SSH children
and synthetic proc files only. It checks target validation, argument/auth policies,
clock skew, parsed counters/rates, heavy query caching, schema/number bounds,
oversized/noisy/invalid streams, strict error classification, no-retry auth failures,
read-only cache aging, publisher crashes and bounded child/process-group cleanup.
Production host connection and optional query availability require separate explicit
acceptance. Tests never connect to configured servers or modify physical devices.
