# Funciones comunes de los scripts de prueba del Lab 1
from scapy.all import get_if_list, checksum


def interfaz():
    # interfaz de red del host 
    return [i for i in get_if_list() if 'eth' in i][0]


def mac_gateway():
    # el host tiene ARP estático hacia su gatewa se usa esa MAC como destino
    with open('/proc/net/arp') as f:
        lineas = f.read().splitlines()[1:]
    return lineas[0].split()[3] if lineas else 'ff:ff:ff:ff:ff:ff'


def checksums_ok(raw_ip):
    # verifica el checksum de la cabecera IP y el del mensaje ICMP
    ihl = (raw_ip[0] & 0x0F) * 4
    total = int.from_bytes(raw_ip[2:4], 'big')
    ip_ok = checksum(raw_ip[:ihl]) == 0
    icmp_ok = checksum(raw_ip[ihl:total]) == 0
    return ip_ok, icmp_ok
