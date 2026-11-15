#!/usr/bin/env python3
# Topologia del Lab 2: 1 switch P4 (s1) y 4 hosts que generan trafico.
# Compila counters.p4, levanta la red en Mininet con BMv2 y carga las
# tablas estaticas desde s1-runtime.json por P4Runtime.
# Uso: sudo python3 topology.py

import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, os.path.join(BASE, '..', 'utils'))

from run_exercise import ExerciseRunner   # utilidades del tutorial de P4

P4_SRC    = 'counters.p4'
P4_JSON   = 'build/counters.json'
P4_INFO   = 'build/counters.p4.p4info.txt'
TOPO_JSON = 'topology.json'

# TOPOLOGIA
#        h1 (s1-p1)
#        h2 (s1-p2)   s1 (switch P4)
#        h3 (s1-p3)
#        h4 (s1-p4)
# Cada host esta en su propia subred y usa como gateway la interfaz del switch
# (ARP estatico). Debe coincidir con HOSTS de generate_runtime.py.
#
# Comandos de cada host:
#  - ruta por defecto y ARP estatico hacia el gateway
#  - IPv6 desactivado: asi no aparece trafico de descubrimiento de vecinos
#  - iptables descarta los ICMP "destination unreachable" y los TCP RST que
#    generaria el kernel del destino al recibir trafico sintetico (UDP/TCP a
#    puertos cerrados). Sin esto esas respuestas se sumarian a los contadores
#    y no se podria comparar contra lo que se inyecto.
COMUN = ["sysctl -w net.ipv6.conf.all.disable_ipv6=1",
         "sysctl -w net.ipv6.conf.default.disable_ipv6=1",
         "iptables -A OUTPUT -p icmp --icmp-type destination-unreachable -j DROP",
         "iptables -A OUTPUT -p tcp --tcp-flags RST RST -j DROP"]


def host(n):
    return {"ip": "10.0.%d.%d/24" % (n, n),
            "mac": "08:00:00:00:%02d:%d%d" % (n, n, n),
            "commands": ["route add default gw 10.0.%d.254 dev eth0" % n,
                         "arp -i eth0 -s 10.0.%d.254 08:00:00:00:%02d:00" % (n, n)] + COMUN}


TOPOLOGY = {
    "hosts": {"h%d" % n: host(n) for n in range(1, 5)},
    "switches": {"s1": {"runtime_json": "s1-runtime.json"}},
    # el sufijo -pN fija el numero de puerto del switch
    "links": [["h%d" % n, "s1-p%d" % n] for n in range(1, 5)]
}


def compilar():
    # compila counters.p4 y genera el p4info que usa P4Runtime
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

    # run_exercise.py lee la topologia desde un JSON
    with open(TOPO_JSON, 'w') as f:
        json.dump(TOPOLOGY, f, indent=2)

    runner = ExerciseRunner(TOPO_JSON, 'logs', 'pcaps', P4_JSON,
                            'simple_switch_grpc', False)
    runner.run_exercise()


if __name__ == '__main__':
    main()
