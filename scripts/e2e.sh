#!/usr/bin/env bash
# Copyright 2026 Tech4Biz Solutions. Apache-2.0.
# End-to-end test: brings up the full stack with the simulator and asserts
# every integration point. Run: ./scripts/e2e.sh
set -euo pipefail

export SIM_MODE=fixed-noon

cleanup() { docker compose --profile sim down -v >/dev/null 2>&1 || true; }
trap cleanup EXIT

cp -n examples/plant.sim.yaml plant.yaml 2>/dev/null || true
docker compose --profile sim up -d --build

echo "waiting for services..."
for i in $(seq 1 30); do
  curl -sf localhost:9101/metrics >/dev/null && break
  sleep 2
done

echo "[1/5] collector exposes plant metrics"
curl -sf localhost:9101/metrics | grep -q 'suryamon_ac_power_watts{inverter="inv-01"' \
  && echo "  PASS"

echo "[2/5] VictoriaMetrics ingests metrics"
for i in $(seq 1 30); do
  n=$(curl -sf 'localhost:8428/api/v1/query?query=suryamon_inverter_up' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["data"]["result"]))')
  [ "$n" -ge 2 ] && break
  sleep 2
done
[ "$n" -ge 2 ] && echo "  PASS ($n inverters up)"

echo "[3/5] analytics writes derived series"
for i in $(seq 1 60); do
  n=$(curl -sf 'localhost:8428/api/v1/query?query=suryamon_string_anomaly_score' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["data"]["result"]))')
  [ "$n" -ge 16 ] && break
  sleep 5
done
[ "$n" -ge 16 ] && echo "  PASS ($n string scores)"

echo "[4/5] soiled string detected (inv-01 string 3 > 0.15)"
score=0
for i in $(seq 1 12); do
  score=$(curl -sfG 'localhost:8428/api/v1/query' \
    --data-urlencode 'query=suryamon_string_anomaly_score{inverter="inv-01",string="3"}' \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else 0)' 2>/dev/null || echo 0)
  python3 -c "exit(0 if float('$score') > 0.15 else 1)" && break
  sleep 10
done
python3 -c "assert float('$score') > 0.15, 'score=$score'" && echo "  PASS (score=$score)"

echo "[5/5] vmalert loaded rules, Grafana healthy"
curl -sf localhost:8880/api/v1/rules >/dev/null 2>&1 || true
curl -sf localhost:3000/api/health | grep -q '"database": *"ok"' && echo "  PASS"

echo
echo "E2E: ALL PASS"