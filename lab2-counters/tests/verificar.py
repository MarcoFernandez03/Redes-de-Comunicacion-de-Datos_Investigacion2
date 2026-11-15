#!/usr/bin/env python3
"""Compara lo que conto el switch con lo que inyecto generar_trafico.py.

Uso:
    python3 tests/verificar.py --antes a.json --despues b.json --esperado e.jsonl
    python3 tests/verificar.py --despues b.json --elefante 10.0.1.1>10.0.4.4 \\
                               --no-elefante 10.0.1.1>10.0.2.2

a.json y b.json son lecturas de `controller.py --snapshot`. Compara las
diferencias (despues - antes) por flujo, por protocolo y el histograma de
tamanos. Termina con codigo 0 si todo coincide.
"""
import argparse
import json
import sys

CUBETAS = ['<=64', '65-128', '129-512', '513-1024', '>1024']


def cubeta(largo):
    for i, tope in enumerate((64, 128, 512, 1024)):
        if largo <= tope:
            return i
    return 4


def cargar_esperado(ruta):
    flujos, protos, hist, mayor = {}, {}, [0] * 5, 0
    with open(ruta) as f:
        for linea in f:
            if not linea.strip():
                continue
            e = json.loads(linea)
            n, b = e['paquetes'], e['paquetes'] * e['bytes_por_paquete']
            k = '%s>%s' % (e['src'], e['dst'])
            p0, b0 = flujos.get(k, (0, 0))
            flujos[k] = (p0 + n, b0 + b)
            p0, b0 = protos.get(e['proto'], (0, 0))
            protos[e['proto']] = (p0 + n, b0 + b)
            hist[cubeta(e['bytes_por_paquete'])] += n
            mayor = max(mayor, e['bytes_por_paquete'])
    return flujos, protos, hist, mayor


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--antes')
    ap.add_argument('--despues', required=True)
    ap.add_argument('--esperado')
    ap.add_argument('--elefante', action='append', default=[],
                    help='flujo origen>destino que debe estar marcado')
    ap.add_argument('--no-elefante', action='append', default=[],
                    help='flujo origen>destino que NO debe estar marcado')
    args = ap.parse_args()

    despues = json.load(open(args.despues))
    fallos = 0

    def linea(nombre, esperado, obtenido):
        nonlocal fallos
        ok = esperado == obtenido
        fallos += 0 if ok else 1
        print(' %-30s esperado %-18s obtenido %-18s %s'
              % (nombre, esperado, obtenido, 'OK' if ok else 'FALLA'))

    if args.esperado:
        antes = json.load(open(args.antes))
        flujos, protos, hist, mayor = cargar_esperado(args.esperado)

        print('Flujos (paquetes/bytes), diferencia de contadores directos:')
        todos = set(flujos) | set(despues['flujos'])
        for k in sorted(todos):
            d = despues['flujos'].get(k, {'paquetes': 0, 'bytes': 0})
            a = antes['flujos'].get(k, {'paquetes': 0, 'bytes': 0})
            obt = (d['paquetes'] - a['paquetes'], d['bytes'] - a['bytes'])
            esp = flujos.get(k, (0, 0))
            if esp != (0, 0) or obt != (0, 0):
                linea(k.replace('>', ' -> '), '%d/%d' % esp, '%d/%d' % obt)

        print('\nProtocolos (paquetes/bytes), diferencia del contador global:')
        for p in ('tcp', 'udp', 'icmp', 'otros'):
            d, a = despues['protocolos'][p], antes['protocolos'][p]
            obt = (d['paquetes'] - a['paquetes'], d['bytes'] - a['bytes'])
            linea(p.upper(), '%d/%d' % protos.get(p, (0, 0)), '%d/%d' % obt)

        print('\nHistograma de tamanos (register), diferencia:')
        for i, etiqueta in enumerate(CUBETAS):
            linea(etiqueta + ' B', hist[i],
                  despues['tamanos']['hist'][i] - antes['tamanos']['hist'][i])
        ok_max = despues['tamanos']['maximo'] >= mayor
        fallos += 0 if ok_max else 1
        print(' %-30s >= %-18s obtenido %-18s %s'
              % ('tamano maximo', mayor, despues['tamanos']['maximo'],
                 'OK' if ok_max else 'FALLA'))

        # trafico que no es de los flujos esperados
        extra = despues['sin_entrada']['paquetes'] - antes['sin_entrada']['paquetes']
        linea('\nIPv4 sin entrada en flujos', 0, extra)

    if args.elefante or args.no_elefante:
        print('\nDeteccion de flujos elefante (umbral %d bytes):' % despues['umbral'])
        for k in args.elefante:
            f = despues['flujos'][k]
            linea(k.replace('>', ' -> ') + ' marcado', True, f['elefante'])
            print('    bytes acumulados en el register: %d' % f['bytes_registro'])
        for k in args.no_elefante:
            f = despues['flujos'][k]
            linea(k.replace('>', ' -> ') + ' marcado', False, f['elefante'])

    print('\nRESULTADO: %s' % ('TODO CORRECTO' if fallos == 0 else '%d diferencia(s)' % fallos))
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
