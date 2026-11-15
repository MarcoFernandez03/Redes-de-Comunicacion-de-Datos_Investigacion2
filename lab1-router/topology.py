#!/usr/bin/env python3
# Topología del Lab  3 routers P4 (s1, s2, s3) y 4 hosts
# Compila router.p4, levanta la red en Mininet con BMv2 y carga las
# tablas estáticasdesde sX-runtime.json por P4Runtime.
# Uso sudo python3 topology.py

import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, os.path.join(BASE, '..', 'utils'))

from run_exercise import ExerciseRunner   # utilidades del tutorial de P4

P4_SRC   = 'router.p4'
P4_JSON  = 'build/router.json'
P4_INFO  = 'build/router.p4.p4info.txt'
TOPO_JSON = 'topology.json'

# TOPOLOGIA
# h1 -- s1 -- s2 -- s3 -- h3
#             |      +--- h4
#             h2
# Cada host usa como gateway la interfaz de su router, con ARP estático
TOPOLOGY = {
    "hosts": {
        "h1": {"ip": "10.0.1.1/24", "mac": "08:00:00:00:01:11",
               "commands": ["route add default gw 10.0.1.254 dev eth0",
                            "arp -i eth0 -s 10.0.1.254 08:00:00:00:01:00"]},
        "h2": {"ip": "10.0.2.2/24", "mac": "08:00:00:00:02:22",
               "commands": ["route add default gw 10.0.2.254 dev eth0",
                            "arp -i eth0 -s 10.0.2.254 08:00:00:00:02:00"]},
        "h3": {"ip": "10.0.3.3/24", "mac": "08:00:00:00:03:33",
               "commands": ["route add default gw 10.0.3.254 dev eth0",
                            "arp -i eth0 -s 10.0.3.254 08:00:00:00:03:01"]},
        "h4": {"ip": "10.0.4.4/24", "mac": "08:00:00:00:04:44",
               "commands": ["route add default gw 10.0.4.254 dev eth0",
                            "arp -i eth0 -s 10.0.4.254 08:00:00:00:03:02"]}
    },
    "switches": {
        "s1": {"runtime_json": "s1-runtime.json"},
        "s2": {"runtime_json": "s2-runtime.json"},
        "s3": {"runtime_json": "s3-runtime.json"}
    },
    # el sufijo -pN fija el número de puerto del router
    "links": [
        ["h1", "s1-p1"], ["s1-p2", "s2-p2"],
        ["h2", "s2-p1"], ["s2-p3", "s3-p3"],
        ["h3", "s3-p1"], ["h4", "s3-p2"]
    ]
}


def compilar():
    # compila router.p4 y genera el p4info que usa P4Runtime
    print('Compilando %s ...' % P4_SRC)
    subprocess.run(['p4c-bm2-ss', '--p4v', '16',
                    '--p4runtime-files', P4_INFO,
                    '-o', P4_JSON, P4_SRC], check=True)


def main():
    if os.geteuid() != 0:
        sys.exit('Ejecutar con sudo: sudo python3 topology.py')

    for d in ('build', 'pcaps', 'logs'):
        os.makedirs(d, exist_ok=True)

    compilar()

    # run_exercise.py lee la topología desde un JSON
    with open(TOPO_JSON, 'w') as f:
        json.dump(TOPOLOGY, f, indent=2)

    runner = ExerciseRunner(TOPO_JSON, 'logs', 'pcaps', P4_JSON,
                            'simple_switch_grpc', False)
    runner.run_exercise()


if __name__ == '__main__':
    main()
