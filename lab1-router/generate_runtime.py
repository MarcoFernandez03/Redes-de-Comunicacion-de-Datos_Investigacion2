#!/usr/bin/env python3
"""Genera s1/s2/s3-runtime.json con las rutas estáticaspara el Lab 1."""
import json

P4INFO = "build/router.p4.p4info.txt"
BMV2   = "build/router.json"

# (prefijo, puerto de salida, MAC destino del siguiente salto)
ROUTES = {
    "s1": [("10.0.1.0", 1, "08:00:00:00:01:11"),
           ("10.0.2.0", 2, "08:00:00:02:01:00"),
           ("10.0.3.0", 2, "08:00:00:02:01:00"),
           ("10.0.4.0", 2, "08:00:00:02:01:00")],
    "s2": [("10.0.1.0", 2, "08:00:00:01:02:00"),
           ("10.0.2.0", 1, "08:00:00:00:02:22"),
           ("10.0.3.0", 3, "08:00:00:03:02:00"),
           ("10.0.4.0", 3, "08:00:00:03:02:00")],
    "s3": [("10.0.1.0", 3, "08:00:00:02:03:00"),
           ("10.0.2.0", 3, "08:00:00:02:03:00"),
           ("10.0.3.0", 1, "08:00:00:00:03:33"),
           ("10.0.4.0", 2, "08:00:00:00:04:44")],
}

# puerto de salida -> MAC de esa interfaz del router
EGRESS = {
    "s1": {1: "08:00:00:00:01:00", 2: "08:00:00:01:02:00"},
    "s2": {1: "08:00:00:00:02:00", 2: "08:00:00:02:01:00", 3: "08:00:00:02:03:00"},
    "s3": {1: "08:00:00:00:03:01", 2: "08:00:00:00:03:02", 3: "08:00:00:03:02:00"},
}

for sw in ROUTES:
    entries = [{
        "table": "MyIngress.ipv4_lpm",
        "default_action": True,
        "action_name": "MyIngress.drop",
        "action_params": {}
    }]
    for prefix, port, mac in ROUTES[sw]:
        entries.append({
            "table": "MyIngress.ipv4_lpm",
            "match": {"hdr.ipv4.dstAddr": [prefix, 24]},
            "action_name": "MyIngress.ipv4_forward",
            "action_params": {"dstAddr": mac, "port": port}
        })
    for port, mac in EGRESS[sw].items():
        entries.append({
            "table": "MyEgress.egress_mac",
            "match": {"standard_metadata.egress_port": port},
            "action_name": "MyEgress.set_src_mac",
            "action_params": {"srcAddr": mac}
        })
    out = {"target": "bmv2", "p4info": P4INFO, "bmv2_json": BMV2,
           "table_entries": entries}
    with open(f"{sw}-runtime.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"{sw}-runtime.json generado ({len(entries)} entradas)")
