#!/usr/bin/env python3
# Captura ICMP echo request en el host y muestra TTL, MAC y checksum usa Scapy
# Uso: python3 tests/recibir.py --count 3 --timeout 8
import argparse
from scapy.all import Ether, IP, ICMP, sniff
from util import interfaz, checksums_ok

p = argparse.ArgumentParser(description='Captura ICMP echo request')
p.add_argument('--count', type=int, default=3)
p.add_argument('--timeout', type=int, default=8)
args = p.parse_args()

iface = interfaz()


def mostrar(pkt):
    ip_ok, icmp_ok = checksums_ok(bytes(pkt.original)[14:])
    print('TTL=%d  %s -> %s  | MAC %s -> %s  | checksum IP %s, ICMP %s' % (
        pkt[IP].ttl, pkt[IP].src, pkt[IP].dst,
        pkt[Ether].src, pkt[Ether].dst,
        'ok' if ip_ok else 'MAL', 'ok' if icmp_ok else 'MAL'), flush=True)


print('Escuchando en %s ...' % iface, flush=True)
capturados = sniff(iface=iface, count=args.count, timeout=args.timeout,
                   lfilter=lambda x: x.haslayer(ICMP) and x[ICMP].type == 8,
                   prn=mostrar)
if len(capturados) == 0:
    print('Ningún paquete recibido', flush=True)
