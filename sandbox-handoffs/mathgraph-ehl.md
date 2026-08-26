# Handoff: mathgraph-ehl

## Outcome: left open — not closable from this environment

**Numbers changed:** none. **Code changed:** none. This session made no
edits to the working tree; every file `git status` shows modified was
already modified before this session started (pre-existing uncommitted
work, not touched further here — see "Pre-existing tree state" below).

## What the bead asked for

mathgraph-ehl asks for a *fix* to `sandbox.sh`'s docker volume mounts
(`claude-uv-cache` → `/home/node/.cache/uv`, `claude-uv-python` →
`/home/node/.local/share/uv/python`), which come up root-owned and break
`uv run` for the non-root `node` user every worker runs as. The bead is
explicit about what would close it: **a real docker run transcript** showing
either (a) relocating the mounts avoids root ownership, or (b) a one-off
chown-via-throwaway-container prep step actually leaves the volume writable
by uid 1000 on the *next* container's mount — not just the one that ran the
chown. It explicitly rejects shipping a fix "on reasoning alone."

## Why it can't be closed here

This worker container has no way to produce that evidence:

```
$ which docker            → (nothing, not found)
$ docker version           → bash: docker: command not found (rc=127)
$ ls -la /var/run/docker.sock → No such file or directory
$ sudo -n true              → bash: sudo: command not found (rc=127)
$ whoami / id                → node, uid=1000(node) gid=1000(node)
```

This container is itself **one of the workers `sandbox.sh` spawns** (per
`sandbox.sh`'s own comments — it's the host-side script that launches
`docker run ... claude -p "$1"` for each bead). A worker cannot run
`sandbox.sh` or test changes to its docker invocation, because the worker
has no docker client, no socket, and no root. This matches exactly what the
bead already anticipated: it says mathgraph-rq3 "deliberately did NOT
attempt" the volume/image-level fix for this same reason, and that
"this sandbox has no docker binary" — confirmed still true.

There is no way to route around this from inside a container: fixing
`sandbox.sh` requires running it (or at minimum running `docker run ... -v
claude-uv-cache:/fix busybox chown ...` by hand) against real Docker, on the
host, outside any worker.

## Prior work check

Per the task instructions, I checked whether a previous worker had claimed
this bead and left partial work:

- `bd show mathgraph-ehl` showed status `OPEN` (not `in_progress`) before I
  claimed it — no prior worker was mid-task.
- `git log --oneline -- sandbox.sh` → empty (never committed to/from in this
  repo's history from a bead session).
- `git diff HEAD -- sandbox.sh` → empty. Untouched.
- The only pre-existing uncommitted change touching this area is
  `sandbox-prompt.md`'s troubleshooting note (the `UV_CACHE_DIR=/tmp/...`
  workaround), which the bead itself attributes to `mathgraph-rq3`, a
  **different, earlier bead** — not partial work on mathgraph-ehl. I left it
  as-is: the bead says to revert/reduce that note only once the underlying
  volume fix has actually landed, which it has not.

## What I did instead of guessing

Nothing to sandbox.sh. Per this repo's standing rule ("a passing test with a
name is evidence; reasoning is not") and the bead's explicit instruction not
to ship a volume-mount change "on reasoning alone" without a real docker
run, I did not edit `sandbox.sh`. Any patch I could write here (e.g.
relocating the volumes, or adding a chown prep step) would be exactly the
untested, reasoning-only change the bead was filed to prevent.

## Pre-existing tree state (not mine, not touched)

`git status --short` at session start already showed modifications to
`.beads/interactions.jsonl`, `.beads/issues.jsonl`, `README.md`,
`sandbox-prompt.md`, `tests/test_corpus.py`, plus an untracked
`.claude/settings.local.json`. These predate this session (visible in the
gitStatus block handed to me at launch) and belong to other beads' work
(e.g. the "re-measure every published number" commit history, mathgraph-rq3's
sandbox-prompt.md note). I did not run the test suite or touch any of these
files, since this bead's scope is `sandbox.sh` / docker volume ownership
only, and none of the changes needed for it require running tests.

## bd state

- Claimed: `bd update mathgraph-ehl --claim` (done this session).
- **Left open** — not closed, not closed-with-reason. This is a genuine
  "cannot verify from here" case per the task instructions, not a queue-
  clearing close.
- Notes recorded on the bead via `bd update mathgraph-ehl --notes=...`
  summarizing the above (no docker access, no prior partial work, no code
  changed).

## What would actually close this

Someone (or an agent) with real docker access to the host running
`sandbox.sh` needs to:

1. Try relocating the volume mounts (e.g. to a path under `/tmp` or a
   differently-initialized named volume) and check post-mount ownership
   with a throwaway container.
2. If relocation alone doesn't fix ownership, test a one-off
   `docker run --rm -v claude-uv-cache:/fix -v claude-uv-python:/fix2
   busybox chown -R 1000:1000 /fix /fix2` prep step, then confirm — in a
   **separate, subsequent** `docker run` mounting the same volumes — that
   the ownership fix persisted (this is the part that's easy to get wrong:
   a chown that "worked" only because it ran in the same container instance
   proves nothing).
3. Land whichever approach empirically works in `sandbox.sh`.
4. Only then, reduce or remove the `sandbox-prompt.md` workaround note
   (currently uncommitted, added by mathgraph-rq3) since it would no longer
   be needed on every worker.

## Test suite

Not run this session — out of scope for this bead (no code was changed that
would affect it), and per the task instructions, the suite should only be
run/reported when it's relevant to the bead in hand.

## Commands for a human to run next (none required by this session)

No commit is proposed — nothing was changed. If the pre-existing
uncommitted changes from other beads (README.md, sandbox-prompt.md,
tests/test_corpus.py, .beads/*) need to be committed, that's a decision for
whichever bead owns them, not this one.

---

## Second worker (2026-08-08, same day): independent re-verification, same conclusion

I picked this bead up while it was already `in_progress` (claimed by the
worker whose handoff is above). Per the task instructions I did not trust
that prior work was correct without checking, so I independently re-ran the
diagnostics myself rather than just reading the notes:

```
$ which docker                          → (empty, not found)
$ ls -la /var/run/docker.sock            → No such file or directory
$ sudo -n true                           → sudo: command not found (rc=127)
$ whoami / id                            → node, uid=1000(node) gid=1000(node), groups=1000(node)
$ ls -la /home/node/.cache                → uv/ owned root:root
$ ls -la /home/node/.local/share          → uv/ owned root:root
$ ls -la /home/node/.claude               → node:node (sibling, non-mounted, for contrast)
```

This reproduces both halves of the bead's claim from scratch: no docker
access from this container, *and* the actual on-disk symptom (named-volume
paths root-owned, non-mounted sibling paths node-owned) is really present
right now, not just asserted.

Additionally checked something the first handoff didn't state explicitly:
whether `sandbox.sh` is even a file this repo's git history could carry a fix
through.

```
$ git -C /workspace ls-files | grep -i sandbox   → sandbox-prompt.md only
$ git -C /workspace log --all -- sandbox.sh       → (empty)
```

`sandbox.sh` is present on disk at `/workspace/sandbox.sh` but is **not a
git-tracked file in this repo** — it's outer harness infrastructure sitting
alongside the checkout, not repo content. This doesn't change the bead's
disposition (it still needs a real docker run to produce evidence, from
outside any worker), but it's worth flagging: even if this session *could*
produce a validated fix, editing `/workspace/sandbox.sh` directly wouldn't be
something `git status`/a PR against this repo would ever show. Wherever
`sandbox.sh`'s real source of truth lives (outside this checkout), the fix
needs to land there.

Checked for partial work left by the first worker before continuing, per
task instructions: `git status --short` shows only the same pre-existing,
unrelated changes noted above (README.md, sandbox-prompt.md,
tests/test_corpus.py, mathgraph/freeze_bench.py, .beads/*, untracked
`.claude/settings.local.json`) — nothing touching `sandbox.sh`, confirming no
code was written on this bead by anyone.

**Outcome: still left open, still no code changes.** Updated the bead's
notes (`bd update mathgraph-ehl --notes=...`) with this independent
confirmation so a third worker doesn't have to re-derive the same answer from
zero — though the honest expectation is that a third worker *in this same
kind of sandbox* will hit the identical wall, because the blocker is
structural (no docker in worker containers), not a gap in investigation.
This bead should stay open until it's picked up by something with actual
docker access to the host, not another worker container.

No test suite run this session either — same reasoning as above, no code
changed, bead scope is docker/infra only.

---

## Third worker (2026-08-08, same day): independent re-verification, same wall, recommend removing from sandbox queue

Picked this up already `in_progress` from the second worker. Did not trust
the prior notes at face value — re-ran the diagnostics from scratch myself:

```
$ which docker                    → exit 1, not found
$ ls -la /var/run/docker.sock     → No such file or directory
$ which sudo                      → exit 1, not found
$ whoami / id                     → node, uid=1000(node) gid=1000(node)
$ ls -la /home/node/.cache        → uv/ drwxr-xr-x root:root
$ ls -la /home/node/.local/share  → uv/ drwxr-xr-x root:root
$ ls -la /home/node/.claude       → node:node (sibling contrast, unchanged)
$ git check-ignore -v sandbox.sh  → .gitignore:33:sandbox.sh sandbox.sh
$ grep -n "uv-cache\|uv-python" sandbox.sh
    53:    -v claude-uv-cache:/home/node/.cache/uv \
    54:    -v claude-uv-python:/home/node/.local/share/uv/python \
```

Every symptom the first two workers found is reproduced exactly, unchanged,
in this container: no docker binary, no socket, no sudo, root-owned mount
paths against node-owned siblings, and `sandbox.sh`'s volume mount lines are
byte-identical to what's already documented above. `git check-ignore`
confirms `sandbox.sh` is gitignored — this repo's checkout structurally
cannot carry a fix to it via a normal commit, which the second worker had
already flagged but which I independently confirmed rather than assumed.

**Outcome: left open, no code changes, no `sandbox.sh` edits.** This is now
the third consecutive worker, in three separate containers, hitting the
identical structural wall (no docker access inside a `sandbox.sh`-spawned
worker) with zero drift in the underlying facts between sessions. There is no
new information a fourth worker-container run would produce — the blocker
isn't a gap in investigation, it's that this bead's evidence bar (a real
`docker run` transcript) is categorically unreachable from inside the thing
`sandbox.sh` spawns.

**Recommendation:** stop dispatching this bead to `sandbox.sh` workers. Either
resolve it from an environment with real docker/host access (a human, or an
agent session running outside a `sandbox.sh` container), or downgrade/park it
(e.g. `bd defer` or a label marking it "needs-host-access") so it stops
consuming worker attempts against a wall that's already been mapped three
times identically. Updated the bead's notes with this session's confirmation
for whoever looks at it next.

No test suite run — bead scope is docker/infra only, no code changed that
could affect it.

---

## Resolved on the HOST, 2026-08-08 (not a worker container)

Three workers stalled because `sandbox.sh` workers have no docker. Run from the
host, where docker is real. Real transcripts, not reasoning:

1. **Reproduced.** `docker run --rm --entrypoint sh -v claude-uv-cache:... claude`
   → `uid=1000(node)`, both mount points `drwxr-xr-x 2 0 0`.
2. **(a) disproven.** A fresh named volume mounted at a *new* path
   (`-v test-uvreloc:/tmp/uv-cache`) also comes up `0 0`. Relocating the mounts
   does nothing — docker inits a volume root-owned when the mount path doesn't
   already exist in the image. The rq3 assumption was wrong; good thing it was
   flagged as untested.
3. **(b) confirmed, including persistence.** `busybox chown -R 1000:1000` in a
   throwaway root container, then a *separate* fresh non-root container sees
   `1000 1000` and `uv run python -c ...` succeeds with **no** UV_CACHE_DIR /
   UV_PYTHON_INSTALL_DIR / XDG_DATA_HOME workaround.
4. **Clean state end-to-end.** Same, starting from volumes that did not exist:
   create → chown → fresh container → `uv run` OK.

Landed: one-off chown prep step in `sandbox.sh` above `run_worker()` (idempotent,
no-op after first run, hard-fails the script if it can't chown).
`sandbox-prompt.md` env workaround reduced to a troubleshooting fallback.

Not fixed, cosmetic: uv warns `Failed to hardlink files` because the cache volume
and `/tmp/venv` are different filesystems. Add `-e UV_LINK_MODE=copy` if the noise
ever matters.
