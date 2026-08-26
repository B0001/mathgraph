# Handoff: mathgraph-rq3

## Bead

`mathgraph-rq3` — "uv cache/data dirs under /home/node owned by root, block
'uv run' for the default user without env overrides". **Closed** (not
"already fixed" — real fix landed this session).

## What was wrong, confirmed

Reproduced exactly as filed, before touching anything:

```
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
error: Failed to initialize cache at /home/node/.cache/uv
Caused by: failed to open file /home/node/.cache/uv/CACHEDIR.TAG: Permission denied (os error 13)
```

```
$ whoami; id
node
uid=1000(node) gid=1000(node) groups=1000(node)

$ ls -la /home/node/.cache/ /home/node/.local/share/
drwxr-xr-x 3 root root 4096 Aug  8 21:08 .cache
drwxr-xr-x 2 root root 4096 Aug  7 04:06 uv          # under .cache
drwxr-xr-x 3 root root 4096 Aug  8 21:08 .local/share
drwxr-xr-x 3 root root 4096 Aug  8 21:08 .local/share/uv
```

vs. sibling non-mounted dirs under `/home/node` (`.claude`, `.beads`, `.config`)
which are `node:node` as expected.

## Root cause — corrected from the bead's own filing

The bead guessed the repo's `./Dockerfile` might be the culprit (a
USER/chown ordering issue). **That's wrong** — this repo's `Dockerfile`
builds `mathgraph:0.1.0`, the unrelated k8s batch/CLI image
(`ENTRYPOINT ["mathgraph"]`). It has nothing to do with the agent sandbox
this session runs in.

The actual source is `sandbox.sh`'s own `run_worker()` (line ~53-54, in this
repo, tracked by git):

```bash
-v claude-uv-cache:/home/node/.cache/uv \
-v claude-uv-python:/home/node/.local/share/uv/python \
```

These are Docker **named volumes**, mounted directly onto the exact paths
that came up root-owned. Confirmed this session is itself one of these
workers — `/proc/mounts` shows both paths as separate `ext4` mounts, and
`UV_PROJECT_ENVIRONMENT=/tmp/venv` is set in the live environment, matching
`sandbox.sh` line 50 exactly. So the bug is 100% reproducible from inside
any `sandbox.sh`-launched worker, including this one, live.

## Fix landed

Added the workaround to `sandbox-prompt.md`'s **Environment** section (the
file every worker is prompted with — I'm reading the same copy right now),
so it's documented once instead of rediscovered per session:

```
export UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python XDG_DATA_HOME=/tmp/xdg-data
mkdir -p /tmp/uv-cache /tmp/uv-python /tmp/xdg-data
MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
```

Diff: `sandbox-prompt.md`, Environment section, +19/-2 lines. Also dropped
the "76 tests" figure from the sentence I was already touching — see "Left
alone / not verified" below for why.

**Verified end-to-end**, not just reasoned about:

```
$ export UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python XDG_DATA_HOME=/tmp/xdg-data
$ mkdir -p /tmp/uv-cache /tmp/uv-python /tmp/xdg-data
$ MATHGRAPH_DATA=/workspace/mathgraph-data uv run python -m unittest discover tests
...
Ran 85 tests in 168.205s

OK
```

Full log saved at `/tmp/test-run.log` during this session (container is
disposable, so treat the "85 tests, OK" line above as the durable evidence,
not the log path).

## What I deliberately did NOT do, and why

**Did not fix `sandbox.sh`'s volume mounts at the source** (the bead's
"option 1": fix the container/volume so ownership is right by default,
no env vars needed). I considered relocating the named-volume mount target
to `/tmp/uv-cache` instead of `/home/node/.cache/uv`, on the theory that
`/tmp` being world-writable (`drwxrwxrwt`, confirmed) would sidestep the
ownership problem. **I did not ship that change.** Reasoning: a fresh Docker
named volume's initial ownership is set by the daemon when the mount point
is first populated, not by the permission bits of the parent directory in
the container — relocating the same volume to a different mount path very
plausibly hits the identical root-owned outcome, and I have no way to verify
either way because **this sandbox has no `docker` binary** (`which docker`
→ not found). Shipping an untested infra change on reasoning alone is
exactly what this repo's standard rejects ("a passing test with a name is
evidence; reasoning is not") — doubly so for something that could silently
break the interpreter/wheel caching `sandbox.sh`'s comments say those
volumes exist for.

Filed **`mathgraph-ehl`** for this instead: fix the volume ownership (either
by relocating the mount and confirming it actually works, or via a one-off
`docker run --rm -v claude-uv-cache:/fix ... chown -R 1000:1000` prep step
in `sandbox.sh` before the main loop) from an environment with real `docker`
access, with a real transcript as the closing evidence — not from in here.

**Did not touch the "76 tests" figure beyond deleting it.** The sentence I
was editing in `sandbox-prompt.md` said "76 tests, roughly two minutes"; my
own verification run just showed 85 tests, all passing. That's not
necessarily *the* correct new number to publish — the working tree already
had substantial **uncommitted** changes from other beads before I started
(`git status` at session start showed `README.md` and `tests/test_corpus.py`
modified; `git diff` shows ~138 new lines in `tests/test_corpus.py`
referencing bead `mathgraph-jvx`, unrelated to mine). The 85-test count is a
live snapshot of a shared, in-progress working tree (all `sandbox.sh`
workers share one bind-mounted repo dir), not something I verified as
stable. Rather than publish a number I can't stand behind, I removed the
stale one and said nothing new. Republishing the correct current count is
the stale-175-sweep's job, not this bead's — out of scope, not filed as a
new bead since it's already covered by existing sweep instructions.

**Did not touch `tests/test_corpus.py` or `README.md`'s content** — those
diffs predate this session (other beads' uncommitted work in the shared
tree). Left entirely alone.

## Test-run evidence (final line, verbatim)

```
Ran 85 tests in 168.205s

OK
```

Zero failures — a superset-safe outcome relative to the bead's own closing
bar ("known-good state: the one documented pre-existing failure, and
nothing else"). This session did not introduce any failure; whether the
previously-documented `176 != 175` failure is itself resolved is a
consequence of other beads' uncommitted work already in this tree, not
something this bead touched or should take credit for.

## Files changed this session

```
 M sandbox-prompt.md   (this session's actual change)
 M .beads/issues.jsonl        (bd bookkeeping: mathgraph-rq3 close, mathgraph-ehl create)
 M .beads/interactions.jsonl  (bd bookkeeping)
```

`README.md` and `tests/test_corpus.py` show as modified in `git status` but
were **already modified before this session started** (other beads' work in
the shared working tree) — not touched by me. Verify with
`git log -p sandbox-prompt.md` after commit if you want the isolated diff.

## Suggested commands for a human (not run — git policy is conservative)

```bash
git add sandbox-prompt.md .beads/issues.jsonl .beads/interactions.jsonl
git commit -m "sandbox-prompt.md: document uv cache permission workaround (mathgraph-rq3)"
# README.md / tests/test_corpus.py changes belong to other beads' sessions —
# review/commit those separately, not bundled with this one.
```

## What I could not verify

- Whether relocating `sandbox.sh`'s named volumes (or chowning them via a
  throwaway root container) actually fixes the ownership problem at the
  source — no `docker` access in this sandbox. Left as `mathgraph-ehl`,
  explicitly unresolved, not guessed at.
- Whether 85 is the "real" final test count once all in-flight beads in this
  shared tree land — not this bead's question, flagged above so it isn't
  mistaken for something I verified.
