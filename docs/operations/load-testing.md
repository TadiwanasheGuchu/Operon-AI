# Load testing

`apps/api/scripts/load_test.py` creates N organisations × K SKUs of realistic data through the
same `Store` code the connectors use. For each organisation it times ingestion and detection,
measures latency on key endpoints, and then runs detection for all organisations concurrently.

```bash
cd apps/api
uv run python scripts/load_test.py --orgs 3 --skus 10000 --report load-report.json
```

Use a disposable database. The script writes real rows.

## Results (2026-11-13, single machine, Postgres 16, no tuning)

| Measure | Result |
|---|---|
| Data per organisation | 10k products, 10k supplier terms, 10k stock levels, about 275k daily sales rows (90 days), 500 POs |
| Initial ingest per organisation | 17.9 s median (sales: about 16 s) |
| Detection per organisation | 15.9 s median (about 300 stockout insights and 50 overdue POs) |
| Detection, 3 organisations concurrently | 15.2 s total |
| `GET /intelligence/insights` | 19 ms median |
| `GET /dashboard` | 49 ms median |

During the test, bulk writes moved from row-by-row to `executemany` in 5,000-row chunks. The
2k-SKU run went from 17.5 s to 3.5 s.

## The 50 × 10k target

This is **extrapolated, not measured**: the sandbox's disk allowance doesn't fit about 6.5 GB.
Run it on staging hardware before launch.

- **Initial onboarding** is a one-off full sync of about 18 s per organisation. That's 15 minutes
  if all 50 join at once, sequentially.
- **Steady state:** incremental syncs move only changed rows. Detection at about 16 s per
  organisation, three at a time, takes about 4.5 minutes per cycle for 50 organisations. That's
  well inside the 15-minute sync interval.
- **Reads** stay in milliseconds, because every list query is organisation-scoped and indexed.

Scale-out levers, in order:

1. More worker replicas (`OPERON_WORKER_REPLICAS`). Temporal spreads activities across them.
2. Postgres compute.
3. Incremental detection over only the changed products.
