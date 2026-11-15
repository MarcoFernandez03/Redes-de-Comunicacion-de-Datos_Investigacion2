#!/usr/bin/env python3
"""Genera s1-runtime.json: entradas estaticas de las tablas de counters.p4.

Uso:  python3 generate_runtime.py [--umbral BYTES]

El umbral (bytes acumulados por flujo a partir del cual se marca como
elefante) se puede cambiar aqui o, en caliente, con controller.py --umbral.
"""
import argparse
import json

P4INFO = "build/counters.p4.p4info.txt"
BMV2   = "build/counters.json"

UMBRAL_DEFECTO = 1000000      # 1 MB

# host -> (IP, MAC del host, puerto del switch, MAC de la interfaz del switch)
# Debe coincidir con topology.py
HOSTS = {
    "h1": ("10.0.1.1", "08:00:00:00:01:11", 1, "08:00:00:00:01:00"),
    "h2": ("10.0.2.2", "08:00:00:00:02:22", 2, "08:00:00:00:02:00"),
    "h3": ("10.0.3.3", "08:00:00:00:03:33", 3, "08:00:00:00:03:00"),
    "h4": ("10.0.4.4", "08:00:00:00:04:44", 4, "08:00:00:00:04:00"),
}


def generar(umbral):
    entries = [{
        "table": "MyIngress.ipv4_lpm",
        "default_action": True,
        "action_name": "MyIngress.drop",
        "action_params": {}
    }]

    # una ruta /24 por host
    for ip, mac, port, gw_mac in HOSTS.values():
        prefijo = ip.rsplit(".", 1)[0] + ".0"
        entries.append({
            "table": "MyIngress.ipv4_lpm",
            "match": {"hdr.ipv4.dstAddr": [prefijo, 24]},
            "action_name": "MyIngress.ipv4_forward",
            "action_params": {"srcAddr": gw_mac, "dstAddr": mac, "port": port}
        })

    # un flujo por cada par ordenado (origen, destino) de hosts distintos
    flow_id = 0
    for src in HOSTS:
        for dst in HOSTS:
            if src == dst:
                continue
            entries.append({
                "table": "MyIngress.flujos",
                "match": {"hdr.ipv4.srcAddr": HOSTS[src][0],
                          "hdr.ipv4.dstAddr": HOSTS[dst][0]},
                "action_name": "MyIngress.rastrear_flujo",
                "action_params": {"flow_id": flow_id, "umbral": umbral}
            })
            flow_id += 1
    return {"target": "bmv2", "p4info": P4INFO, "bmv2_json": BMV2,
            "table_entries": entries}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--umbral", type=int, default=UMBRAL_DEFECTO,
                    help="umbral de flujo elefante en bytes (defecto %d)" % UMBRAL_DEFECTO)
    args = ap.parse_args()
    runtime = generar(args.umbral)
    with open("s1-runtime.json", "w") as f:
        json.dump(runtime, f, indent=2)
    print("s1-runtime.json generado (%d entradas, umbral %d bytes)"
          % (len(runtime["table_entries"]), args.umbral))
