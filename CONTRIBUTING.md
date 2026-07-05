# Contributing to Suryamon

We welcome inverter register maps, KPI improvements, dashboards, and alert
rules grounded in real plant operations.

## Development loop (no hardware needed)

```bash
docker compose --profile sim up -d
python -m pytest tests/
```

## Rules

- KPI functions stay pure and tested. No I/O in `kpi.py`.
- Every alert rule documents its physical cause in the annotation.
- Match the SunSpec spec exactly. Cite model and offset in comments.
- One PR per change. Include a simulator scenario if behaviour changes.
