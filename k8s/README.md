# Kubernetes deployment

Batch Jobs over a corpus PVC. Two-phase: `setup` populates the volume once, then
compute Jobs read it.

```bash
docker build -t mathgraph:0.1.0 .
kubectl apply -k k8s/overlays/dev

# setup MUST finish before bench does anything useful
kubectl wait --for=condition=complete job/mathgraph-setup-dev -n mathgraph-dev --timeout=2h
```

| Path | Purpose |
|---|---|
| `base/job-setup.yaml` | Clones mathlib4 + 6 blueprint repos into the PVC |
| `base/job-bench.yaml` | PFR benchmark; initContainer blocks if the corpus is missing |
| `base/pvc.yaml` | 30Gi RWO (60Gi in prod) |

## The corpus is not in the image

`mathgraph setup` git-clones ~8GB. That belongs on a volume, not in a layer — so
`mathgraph-data/` is in `.dockerignore` (without it, every build would upload
all 8GB to the daemon first) and `MATHGRAPH_DATA=/data` is baked in, which is
the default for every command's `--data-dir`. The Jobs pass no `--data-dir` flag
at all.

`git` and `ca-certificates` are installed in the runtime image for this reason —
they are runtime dependencies here, not build tools.

## Ordering

Kubernetes has no cross-Job ordering primitive. Rather than hoping apply order
holds, `job-bench.yaml` runs an initContainer that checks for `/data/artifacts`
and fails immediately with a clear message if setup has not run — instead of
letting the benchmark die on a missing-artifact error minutes in.

## Network egress

`mathgraph-setup` is the only Job needing public internet (github.com over 443).
**If the namespace has a default-deny NetworkPolicy, it needs an explicit allow
rule for TCP/443 plus DNS**, or the clones hang until `activeDeadlineSeconds`
(2h) kills them.

## Before deploying

- The PVC is `ReadWriteOnce`. Several compute Jobs reading in parallel across
  nodes would need `ReadWriteMany` and an RWX-capable storage class; with RWO
  the second pod on another node stays Pending.
- Most storage classes let you expand a PVC but never shrink it, so the prod
  60Gi is effectively one-way.
- Re-running `setup` re-clones from scratch; budget the time and the disk.
