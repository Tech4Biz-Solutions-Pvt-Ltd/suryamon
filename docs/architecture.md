# Suryamon architecture

## Design decisions

**Prometheus metrics model, not a custom database.** Solar telemetry is
time-series data. VictoriaMetrics gives us 2-year retention on a Raspberry
Pi class machine, PromQL for free, and a mature alerting path (vmalert).
We write zero storage code.

**Collector is a dumb pipe.** It reads SunSpec registers and exposes gauges.
No business logic, no state. This makes it trivially testable against the
simulator and safe to restart at any time.

**Analytics is a batch loop, not a stream processor.** IEC 61724-1 KPIs are
periodic aggregates (daily PR, daily yield). A 5-minute compute loop that
queries PromQL and writes derived series back is simpler, debuggable, and
sufficient. Derived series get the same retention and alerting as raw data.

**Honest PR.** Performance Ratio requires plane-of-array irradiation. Plants
without a pyranometer get specific yield only, until the satellite
irradiance integration lands. We never fabricate a PR number.

**Simulator is a first-class component.** Every feature must be demonstrable
with `docker compose --profile sim up`. This keeps the demo path honest and
gives contributors a hardware-free development loop.

## Data flow

1. `collector` polls each inverter every 10s over Modbus TCP, walks the
   SunSpec model chain once per connection, then reads models 103 and 160.
2. `vmagent` scrapes `collector:9101/metrics` and remote-writes to
   VictoriaMetrics.
3. `analytics` runs every 5 minutes: queries trailing-day energy, computes
   IEC 61724-1 KPIs and string anomaly scores, writes them back as new series.
4. `vmalert` evaluates the rule pack every 60s and routes firing alerts to
   Alertmanager.
5. Grafana reads everything from VictoriaMetrics via provisioned dashboards.

## Metric naming

All series carry the `suryamon_` prefix and `plant` label. Raw series add
`inverter`, string-level series add `string`. Derived series add `window`.

## Extending

- New inverter protocol: add a reader module in `collector/`, keep the same
  gauge names.
- New KPI: add a pure function in `analytics/suryamon_analytics/kpi.py` with
  tests, wire it in `service.py`.
- New alert: add a rule to `deploy/vmalert/`, document the physical cause in
  the annotation.
