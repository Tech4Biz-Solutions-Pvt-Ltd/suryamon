# Suryamon

**Open source health monitoring for solar power plants. From inverter to dashboard in one Docker command.**

Solar plants generate data constantly. Most small and mid-size operators never use it. Suryamon collects inverter telemetry over Modbus/SunSpec, computes plant performance per IEC 61724-1, and alerts operators before underperformance costs real money.

## What it does

- **Collects**: Polls any SunSpec-compliant inverter over Modbus TCP/RTU. AC/DC power, per-string currents, voltages, temperatures, energy counters.
- **Computes**: Performance Ratio (PR), Capacity Utilisation Factor (CUF), specific yield, and string-level anomaly scores. Calculations follow IEC 61724-1.
- **Alerts**: Ships with vmalert rules for string underperformance, inverter offline, soiling drift, and PR degradation.
- **Visualises**: Pre-built Grafana dashboards. Plant overview, inverter detail, string heatmap.

## Architecture

```
Inverters (Modbus/SunSpec)
        |
   suryamon-collector  (Python, async, exposes /metrics)
        |
   VictoriaMetrics     (time-series storage)
        |
   +----+----------------+
   |                     |
suryamon-analytics    vmalert
(PR/CUF, IEC 61724)   (alert rules)
   |                     |
   +----> Grafana <------+
```

## Quickstart

```bash
git clone https://github.com/tech4biz-oss/suryamon
cd suryamon
cp examples/plant.example.yaml plant.yaml   # describe your plant
docker compose up -d
```

Open Grafana at `http://localhost:3000` (admin/suryamon). The plant overview dashboard is provisioned automatically.

No physical inverter? Run the simulator:

```bash
docker compose --profile sim up -d
```

The simulator emulates a 100 kWp plant with two SunSpec inverters, realistic irradiance curves, and one deliberately soiled string. You will see alerts fire within minutes.

## Plant configuration

One YAML file describes the plant. The collector and analytics services both read it.

```yaml
plant:
  name: demo-rooftop
  capacity_kwp: 100.0
  location: { lat: 12.97, lon: 77.59, tz: Asia/Kolkata }
inverters:
  - id: inv-01
    host: 192.168.1.40
    port: 502
    unit_id: 1
    strings: 8
```

## Roadmap

- [x] SunSpec Modbus TCP collector
- [x] IEC 61724-1 PR/CUF/specific yield
- [x] Grafana dashboard pack
- [x] vmalert rule pack
- [x] Plant simulator
- [ ] Modbus RTU (serial) support
- [ ] MQTT ingest for edge data loggers
- [ ] Satellite irradiance fallback (no pyranometer required)
- [ ] Multi-plant fleet view

## Why we built this

Commercial solar monitoring platforms are closed, expensive, and out of reach for the operators who need them most. India alone adds over 20 GW of solar capacity a year, much of it in C&I rooftop installations with no monitoring beyond the inverter vendor app. Suryamon gives every operator production-grade observability for free.

Built and maintained by [Tech4Biz Solutions](https://tech4bizsolutions.com). We restore stuck engineering delivery, from silicon to cloud.

## Testing and verification

Every commit runs two CI stages:

1. **Unit and integration tests** (`pytest tests/`): IEC 61724-1 KPI math against reference cases, string anomaly scoring, full SunSpec wire round-trip (simulator server to collector reader over real TCP), and the analytics service against a VictoriaMetrics-compatible API. PromQL in every alert rule and dashboard panel is parsed and validated.
2. **Full-stack e2e** (`./scripts/e2e.sh`): brings up the entire Docker Compose stack with the simulator and asserts collector metrics, VictoriaMetrics ingestion, derived KPI series, soiled-string detection, and Grafana health.

Note: pymodbus is pinned to the 3.6 line. The 3.7+ series is mid-migration to a new server API with breaking changes. We will move when pymodbus 4.0 stabilises.

## License

Apache-2.0
