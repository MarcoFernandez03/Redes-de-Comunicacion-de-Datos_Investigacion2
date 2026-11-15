#!/usr/bin/env python3
# Envía paquetes ICMP echo con el TTL indicadousa Scapy
# Uso: python3 tests/enviar.py 10.0.3.3 --ttl 64 --count 3
import argparse
from scapy.all import Ether, IP, ICMP, Raw, sendp, get_if_hwaddr
from util import interfaz, mac_gateway

p = argparse.ArgumentParser(description='Envía ICMP echo con TTL configurable')
p.add_argument('dst', help='IP destino')
p.add_argument('--ttl', type=int, default=64)
p.add_argument('--count', type=int, default=3)
args = p.parse_args()

iface = interfaz()
trama = (Ether(src=get_if_hwaddr(iface), dst=mac_gateway())
         / IP(dst=args.dst, ttl=args.ttl)
         / ICMP(id=0x1234, seq=1)
         / Raw(b'p4-lab1-prueba!!'))

print('Enviando %d paquete(s) a %s con TTL=%d' % (args.count, args.dst, args.ttl))
sendp(trama, iface=iface, count=args.count, inter=0.2, verbose=0)
