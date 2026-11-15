# Funciones comunes de los scripts de prueba del Lab 2
from scapy.all import get_if_list


def interfaz():
    # interfaz de red del host
    return [i for i in get_if_list() if 'eth' in i][0]


def mac_gateway():
    # el host tiene ARP estatico hacia su gateway: se usa esa MAC como destino
    with open('/proc/net/arp') as f:
        lineas = f.read().splitlines()[1:]
    return lineas[0].split()[3] if lineas else 'ff:ff:ff:ff:ff:ff'
