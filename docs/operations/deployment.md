# Deployment

Images are immutable and tagged by commit. Deploying is one command, or one pipeline, on any
Docker host (ADR 0015). Cloud-specific infrastructure as code waits for the hosting decision.

## Pipeline

1. **CI** (`.github/workflows/ci.yml`) runs on every pull request and push to main: lint, types,
   tests, dependency audit.
2. **Release images** (`release.yml`), on push to main: builds `operon-api` and `operon-web` and
   pushes them to `ghcr.io/<owner>/…:<12-char sha>` and `:main`, with provenance and SBOM.
3. **Deploy staging** (`deploy-staging.yml`): after a successful release, or by hand with a
   version, it runs `deploy.sh staging <sha>` against the staging host over SSH.
4. **Production:** the same command with `production`, run by a person after staging checks,
   from a protected GitHub environment or an operator's machine.

## The stack (`infrastructure/deployment/compose.production.yml`)

| Service | Role |
|---|---|
| `api` | FastAPI, 2 replicas by default, read-only filesystem, all capabilities dropped, readiness health check |
| `worker` | Temporal worker: syncs, detection, workflows, agents, maintenance |
| `web` | Next.js (standalone). Proxies `/api` to `api` on the internal network |
| `caddy` | The only exposed service: automatic TLS certificates, HSTS, compression. Hides health URLs |
| `migrate` | One-off `alembic upgrade head`, run by `deploy.sh` before the rollout |
| `postgres`, `redis`, `temporal` | Optional `self-hosted` profile. Prefer managed services |

## Deploying

On the host, once:

- Docker is installed.
- DNS for `OPERON_DOMAIN` points at the host.
- Ports 80 and 443 are open.
- The host can pull from GHCR (`docker login ghcr.io` with a `read:packages` token).

From your machine or CI:

```bash
export DOCKER_HOST=ssh://deploy@staging.example.com
export OPERON_IMAGE_OWNER=<github owner, lowercase> OPERON_DOMAIN=staging.example.com ACME_EMAIL=ops@example.com
infrastructure/deployment/deploy.sh staging <version>
```

The settings come from `infrastructure/deployment/envs/<environment>.env`, which is git-ignored.
Start from `env.example`, keep secrets in a secret manager, and render the file at deploy time.

`deploy.sh` runs these steps:

1. pull the images;
2. migrate;
3. start the new containers;
4. wait up to 2.5 minutes for every API replica to report healthy;
5. if they don't, roll back automatically to the version that was running before.

## Rules that keep rollback safe

- **Migrations are additive (expand → contract).** Add columns and tables in one release, and
  remove old ones only in a later release, once no running version uses them. That way the
  previous version keeps working after a rollback.
- Never edit a deployed migration. Write a new one.
- Back up, or confirm the PITR window, before a release that rewrites data.
  See [backup-and-recovery.md](backup-and-recovery.md).

## Secrets and keys

- `OPERON_SECRET_KEYS` is a key ring (`v2:…,v1:…`). To rotate, add the new key first. Old
  ciphertexts keep decrypting with their version.
- Database roles: the API uses `operon_app`, which is subject to RLS. Migrations use
  `operon_owner`.
- Model provider keys are optional. Each organisation still opts in to AI.
