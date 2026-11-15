#!/usr/bin/env python3
"""Genera trafico sintetico de un tamano y cantidad exactos con Scapy.

Se ejecuta dentro de un host de Mininet. Ejemplos:
    python3 tests/generar_trafico.py 10.0.2.2 --proto icmp --count 10 --payload 100
    python3 tests/generar_trafico.py 10.0.3.3 --proto udp  --count 20 --payload 200
    python3 tests/generar_trafico.py 10.0.4.4 --proto tcp  --count 25 --payload 500
    python3 tests/generar_trafico.py 10.0.4.4 --proto otros --count 5 --payload 50

Con --esperado ARCHIVO agrega, una linea JSON por flujo, lo que el switch
deberia contar (paquetes y bytes de trama Ethernet). verificar.py lo usa para
comparar contra los contadores del switch.

Notas sobre las respuestas del destino:
  - ICMP: el kernel del destino responde el echo, y esa respuesta tambien
    cruza el switch (flujo inverso, mismo tamano). Se anota como esperado.
  - UDP/TCP/otros: topology.py instala reglas iptables en los hosts que
    descartan las respuestas del kernel (ICMP unreachable, TCP RST), asi que
    no hay trafico de vuelta.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scapy.all import Ether, IP, ICMP, UDP, TCP, Raw, sendp, get_if_addr   # noqa: E402
from util import interfaz, mac_gateway                                      # noqa: E402

PROTOS = {'icmp': 1, 'tcp': 6, 'udp': 17, 'otros': 253}


def construir(proto, src, dst, payload, seq, sport, dport, mac):
    """Una trama Ethernet con el protocolo pedido y `payload` bytes de datos."""
    datos = Raw(b'x' * payload)
    capa_ip = IP(src=src, dst=dst)
    if proto == 'icmp':
        l4 = ICMP(type=8, id=0x1234, seq=seq)
    elif proto == 'udp':
        l4 = UDP(sport=sport, dport=dport)
    elif proto == 'tcp':
        l4 = TCP(sport=sport, dport=dport, flags='A', seq=seq)
    else:                                   # protocolo IP 253 (experimentacion)
        capa_ip = IP(src=src, dst=dst, proto=253)
        return Ether(dst=mac) / capa_ip / datos
    return Ether(dst=mac) / capa_ip / l4 / datos


def main():
    ap = argparse.ArgumentParser(description='Genera trafico sintetico exacto')
    ap.add_argument('destino')
    ap.add_argument('--proto', choices=sorted(PROTOS), default='udp')
    ap.add_argument('--count', type=int, default=10, help='numero de paquetes')
    ap.add_argument('--payload', type=int, default=100, help='bytes de datos')
    ap.add_argument('--intervalo', type=float, default=0.01, help='segundos entre paquetes')
    ap.add_argument('--sport', type=int, default=40000)
    ap.add_argument('--dport', type=int, default=5001)
    ap.add_argument('--esperado', help='archivo donde anotar lo que debe contar el switch')
    args = ap.parse_args()

    iface = interfaz()
    src = get_if_addr(iface)
    mac = mac_gateway()

    tramas = [construir(args.proto, src, args.destino, args.payload, i,
                        args.sport, args.dport, mac) for i in range(args.count)]
    largo = len(tramas[0])
    sendp(tramas, iface=iface, inter=args.intervalo, verbose=False)
    time.sleep(0.3)

    print('ENVIADO %-5s %s -> %s  %d paquetes de %d bytes (%d bytes en total)'
          % (args.proto, src, args.destino, args.count, largo, args.count * largo))

    if args.esperado:
        filas = [{'src': src, 'dst': args.destino, 'proto': args.proto,
                  'paquetes': args.count, 'bytes_por_paquete': largo}]
        if args.proto == 'icmp':            # respuesta del kernel destino
            filas.append({'src': args.destino, 'dst': src, 'proto': 'icmp',
                          'paquetes': args.count, 'bytes_por_paquete': largo})
        with open(args.esperado, 'a') as f:
            for fila in filas:
                f.write(json.dumps(fila) + '\n')


if __name__ == '__main__':
    main()
