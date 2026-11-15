#!/usr/bin/env python3
# Traza de ruta con Scapy, envía ICMP echo con TTL 1..N y muestra quién responde
# Uso: python3 tests/traza.py 10.0.3.3
import argparse
from scapy.all import Ether, IP, ICMP, Raw, srp1, get_if_hwaddr
from util import interfaz, mac_gateway, checksums_ok

p = argparse.ArgumentParser(description='Traza de ruta (ICMP Time Exceeded)')
p.add_argument('dst', help='IP destino')
p.add_argument('--max', type=int, default=8, help='maximo de saltos')
p.add_argument('--timeout', type=float, default=2)
args = p.parse_args()

iface = interfaz()
eth = Ether(src=get_if_hwaddr(iface), dst=mac_gateway())

print('Traza hacia %s (max. %d saltos)' % (args.dst, args.max))
for ttl in range(1, args.max + 1):
    paquete = (eth / IP(dst=args.dst, ttl=ttl)
               / ICMP(id=0x1234, seq=ttl) / Raw(b'p4-lab1-traza!!!'))
    r = srp1(paquete, iface=iface, timeout=args.timeout, verbose=0)
    if r is None or not r.haslayer(ICMP):
        print('%2d  *' % ttl)
        continue
    ip_ok, icmp_ok = checksums_ok(bytes(r.original)[14:])
    tipo = r[ICMP].type
    nombre = {11: 'Time Exceeded', 0: 'Echo Reply'}.get(tipo, 'ICMP tipo %d' % tipo)
    print('%2d  %-12s %-14s (checksum IP %s, ICMP %s)' % (
        ttl, r[IP].src, nombre,
        'ok' if ip_ok else 'MAL', 'ok' if icmp_ok else 'MAL'))
    if tipo == 0:
        break
