#!/usr/bin/env python3
# Copyright 2026 Tech4Biz Solutions. Apache-2.0.
"""Validate every PromQL expression in alert rules and dashboards."""
import json
import sys
import yaml
from promql_parser import parse

errors = []

rules = yaml.safe_load(open("deploy/vmalert/solar-health.yml"))
for g in rules["groups"]:
    for r in g["rules"]:
        try:
            parse(r["expr"])
        except Exception as e:
            errors.append(f"rule {r['alert']}: {e}")

dash = json.load(open("deploy/grafana/dashboards/plant-overview.json"))
for p in dash["panels"]:
    for t in p.get("targets", []):
        try:
            parse(t["expr"])
        except Exception as e:
            errors.append(f"panel {p['title']}: {e}")

if errors:
    print("PROMQL FAILURES:")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("all PromQL expressions valid")
