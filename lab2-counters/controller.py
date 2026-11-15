#!/usr/bin/env python3
"""Controlador del Lab 2: lee periodicamente los contadores y registers de
counters.p4 y los imprime en consola.

Se conecta al switch s1 por P4Runtime (gRPC). Para los registers, si la lectura
por P4Runtime falla, usa como respaldo el cliente Thrift de BMv2
(simple_switch_CLI).

Uso (con la red de topology.py corriendo en otra terminal):
    python3 controller.py                    # imprime cada 5 s
    python3 controller.py --intervalo 2      # cada 2 s
    python3 controller.py --umbral 500000    # cambia el umbral de elefante y sigue
    python3 controller.py --una-vez          # una sola lectura
    python3 controller.py --snapshot x.json  # guarda una lectura en JSON y termina
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, '..', 'utils'))
os.environ.setdefault('GRPC_ENABLE_FORK_SUPPORT', '0')

from p4.v1 import p4runtime_pb2                       # noqa: E402
from p4runtime_lib.helper import P4InfoHelper         # noqa: E402
from p4runtime_lib.bmv2 import Bmv2SwitchConnection   # noqa: E402

# Nombres en el P4 (control MyIngress)
T_FLUJOS     = 'MyIngress.flujos'
A_RASTREAR   = 'MyIngress.rastrear_flujo'
C_PROTO      = 'MyIngress.proto_counter'
C_SIN_ENTRADA = 'MyIngress.flujos_sin_entrada'
C_ELEFANTE   = 'MyIngress.elefante_ctr'
R_HIST       = 'MyIngress.size_hist'
R_LAST       = 'MyIngress.size_last'
R_MAX        = 'MyIngress.size_max'
R_SUM        = 'MyIngress.size_sum'
R_FLUJO_BYTES = 'MyIngress.flujo_bytes'
R_ELEFANTE   = 'MyIngress.elefante_flag'

# orden de IDX_* en counters.p4
PROTOCOLOS = ['tcp', 'udp', 'icmp', 'otros', 'no_ipv4']
NOMBRES_PROTO = {'tcp': 'TCP', 'udp': 'UDP', 'icmp': 'ICMP',
                 'otros': 'Otros (IPv4)', 'no_ipv4': 'No IPv4'}
CUBETAS = ['<= 64 B', '65-128 B', '129-512 B', '513-1024 B', '> 1024 B']
MAX_FLUJOS = 64


class Switch(object):
    """Lecturas P4Runtime (y Thrift como respaldo) sobre el switch."""

    def __init__(self, args):
        self.args = args
        self.helper = P4InfoHelper(args.p4info)
        self.device_id = args.device_id
        self.sw = Bmv2SwitchConnection(name='s1', address=args.grpc,
                                       device_id=args.device_id)
        self.stub = self.sw.client_stub
        self.election_id = int(time.time())
        self._primario = False
        self.usar_thrift = False
        self._ids_match = None

    def cerrar(self):
        self.sw.shutdown()

    # ---------------------------------------------------------------- tablas
    def _nombres_match(self):
        # id de campo de match -> 'src' / 'dst'
        if self._ids_match is None:
            tabla = self.helper.get('tables', name=T_FLUJOS)
            self._ids_match = {}
            for mf in tabla.match_fields:
                self._ids_match[mf.id] = 'src' if mf.name.endswith('srcAddr') else 'dst'
        return self._ids_match

    def _clave_flujo(self, match):
        ids = self._nombres_match()
        campos = {}
        for m in match:
            campos[ids[m.field_id]] = socket.inet_ntoa(m.exact.value)
        return campos['src'], campos['dst']

    def _leer(self, entidad_setter):
        req = p4runtime_pb2.ReadRequest()
        req.device_id = self.device_id
        entidad_setter(req.entities.add())
        for resp in self.stub.Read(req):
            for ent in resp.entities:
                yield ent

    def entradas_flujos(self):
        """{(src, dst): (flow_id, umbral)} de las entradas de la tabla flujos."""
        tabla_id = self.helper.get_tables_id(T_FLUJOS)
        accion = self.helper.get('actions', name=A_RASTREAR)
        param = {p.id: p.name for p in accion.params}
        res = {}

        def setter(e):
            e.table_entry.table_id = tabla_id

        for ent in self._leer(setter):
            te = ent.table_entry
            if te.action.action.action_id != accion.preamble.id:
                continue
            vals = {param[p.param_id]: int.from_bytes(p.value, 'big')
                    for p in te.action.action.params}
            res[self._clave_flujo(te.match)] = (vals['flow_id'], vals['umbral'])
        return res

    def contadores_flujos(self):
        """{(src, dst): (paquetes, bytes)} leyendo los direct counters."""
        tabla_id = self.helper.get_tables_id(T_FLUJOS)
        res = {}
        try:
            def setter(e):
                e.direct_counter_entry.table_entry.table_id = tabla_id
            for ent in self._leer(setter):
                dc = ent.direct_counter_entry
                res[self._clave_flujo(dc.table_entry.match)] = (
                    dc.data.packet_count, dc.data.byte_count)
            if res:
                return res
        except Exception:
            pass
        # Respaldo: leer las entradas de la tabla pidiendo counter_data
        def setter2(e):
            e.table_entry.table_id = tabla_id
            e.table_entry.counter_data.SetInParent()
        for ent in self._leer(setter2):
            te = ent.table_entry
            res[self._clave_flujo(te.match)] = (
                te.counter_data.packet_count, te.counter_data.byte_count)
        return res
    
    def _ser_primario(self):
        """Arbitraje P4Runtime con un election id propio (necesario para escribir)."""
        if self._primario:
            return
        req = p4runtime_pb2.StreamMessageRequest()
        req.arbitration.device_id = self.device_id
        req.arbitration.election_id.high = 0
        req.arbitration.election_id.low = self.election_id
        self.sw.requests_stream.put(req)
        self.sw.dispatcher.arbitration_queue.get(timeout=10)
        self._primario = True

    def fijar_umbral(self, umbral):
        """Modifica el umbral de elefante en todas las entradas de flujos."""
        self._ser_primario()
        n = 0
        for (src, dst), (flow_id, _) in self.entradas_flujos().items():
            entrada = self.helper.buildTableEntry(
                table_name=T_FLUJOS,
                match_fields={'hdr.ipv4.srcAddr': src, 'hdr.ipv4.dstAddr': dst},
                action_name=A_RASTREAR,
                action_params={'flow_id': flow_id, 'umbral': umbral})
            req = p4runtime_pb2.WriteRequest()
            req.device_id = self.device_id
            req.election_id.low = self.election_id
            up = req.updates.add()
            up.type = p4runtime_pb2.Update.MODIFY
            up.entity.table_entry.CopyFrom(entrada)
            self.stub.Write(req)
            n += 1
        return n

    # ------------------------------------------------------------ contadores
    def contador(self, nombre, n):
        """Lista de n tuplas (paquetes, bytes) de un contador indirecto."""
        cid = self.helper.get_counters_id(nombre)
        res = [(0, 0)] * n

        def setter(e):
            e.counter_entry.counter_id = cid
        vistos = 0
        try:
            for ent in self._leer(setter):
                ce = ent.counter_entry
                res[ce.index.index] = (ce.data.packet_count, ce.data.byte_count)
                vistos += 1
        except Exception:
            vistos = 0
        if vistos < n:                       # respaldo: indice por indice
            for i in range(n):
                def setter_i(e, i=i):
                    e.counter_entry.counter_id = cid
                    e.counter_entry.index.index = i
                for ent in self._leer(setter_i):
                    ce = ent.counter_entry
                    res[i] = (ce.data.packet_count, ce.data.byte_count)
        return res

    # ------------------------------------------------------------- registers
    def registro(self, nombre, n):
        """Lista de n enteros de un register."""
        if not self.usar_thrift:
            try:
                return self._registro_p4runtime(nombre, n)
            except Exception as e:
                print('[aviso] lectura de registers por P4Runtime fallo (%s); '
                      'uso Thrift' % type(e).__name__, file=sys.stderr)
                self.usar_thrift = True
        return self._registro_thrift(nombre, n)

    def _registro_p4runtime(self, nombre, n):
        rid = self.helper.get_registers_id(nombre)
        res = [None] * n

        def setter(e):
            e.register_entry.register_id = rid
        for ent in self._leer(setter):
            re_ = ent.register_entry
            res[re_.index.index] = int.from_bytes(re_.data.bitstring, 'big')
        if any(v is None for v in res):      # respaldo: indice por indice
            for i in range(n):
                def setter_i(e, i=i):
                    e.register_entry.register_id = rid
                    e.register_entry.index.index = i
                for ent in self._leer(setter_i):
                    res[i] = int.from_bytes(ent.register_entry.data.bitstring, 'big')
        if any(v is None for v in res):
            raise RuntimeError('register incompleto')
        return res

    def _registro_thrift(self, nombre, n):
        cmds = ''.join('register_read %s %d\n' % (nombre, i) for i in range(n))
        out = subprocess.run(['simple_switch_CLI', '--thrift-port',
                              str(self.args.thrift_port)],
                             input=cmds, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, universal_newlines=True).stdout
        res = [0] * n
        for idx, val in re.findall(r'\[(\d+)\]\s*=\s*(\d+)', out):
            if int(idx) < n:
                res[int(idx)] = int(val)
        return res


# ------------------------------------------------------------------- muestras
def tomar_muestra(sw):
    """Lee todo el estado del switch y lo devuelve como un diccionario."""
    flujos_ctr = sw.contadores_flujos()
    entradas = sw.entradas_flujos()
    bytes_reg = sw.registro(R_FLUJO_BYTES, MAX_FLUJOS)
    flags = sw.registro(R_ELEFANTE, MAX_FLUJOS)
    proto = sw.contador(C_PROTO, len(PROTOCOLOS))
    sin_entrada = sw.contador(C_SIN_ENTRADA, 1)[0]
    elef_ctr = sw.contador(C_ELEFANTE, 1)[0]
    umbral = max([u for (_, u) in entradas.values()] or [0])

    flujos = {}
    for (src, dst), (fid, _) in entradas.items():
        pk, by = flujos_ctr.get((src, dst), (0, 0))
        flujos['%s>%s' % (src, dst)] = {
            'paquetes': pk, 'bytes': by, 'flow_id': fid,
            'bytes_registro': bytes_reg[fid], 'elefante': bool(flags[fid])}

    return {
        'timestamp': time.time(),
        'flujos': flujos,
        'protocolos': {p: {'paquetes': proto[i][0], 'bytes': proto[i][1]}
                       for i, p in enumerate(PROTOCOLOS)},
        'sin_entrada': {'paquetes': sin_entrada[0], 'bytes': sin_entrada[1]},
        'trafico_elefante': {'paquetes': elef_ctr[0], 'bytes': elef_ctr[1]},
        'tamanos': {'hist': sw.registro(R_HIST, len(CUBETAS)),
                    'ultimo': sw.registro(R_LAST, 1)[0],
                    'maximo': sw.registro(R_MAX, 1)[0],
                    'suma': sw.registro(R_SUM, 1)[0]},
        'umbral': umbral,
    }


# ------------------------------------------------------------------- consola
def fmt_n(n):
    return '{:,}'.format(n)


def fmt_tasa(delta_bytes, dt):
    if dt <= 0:
        return '-'
    return '%.1f' % (delta_bytes * 8 / dt / 1000.0)     # kbit/s


def imprimir(m, previa, n, intervalo, todos):
    dt = m['timestamp'] - previa['timestamp'] if previa else 0
    hora = time.strftime('%H:%M:%S', time.localtime(m['timestamp']))
    print('=' * 78)
    print(' s1 | %s | lectura #%d | intervalo %.1f s | umbral elefante %s B'
          % (hora, n, intervalo, fmt_n(m['umbral'])))
    print('=' * 78)

    # --- protocolos
    print('\nContadores globales por protocolo (ingreso)')
    print(' %-14s %12s %14s %10s %12s' % ('Protocolo', 'Paquetes', 'Bytes', '+Paquetes', '+Bytes'))
    for p in PROTOCOLOS:
        a = m['protocolos'][p]
        b = previa['protocolos'][p] if previa else {'paquetes': 0, 'bytes': 0}
        print(' %-14s %12s %14s %10s %12s' % (
            NOMBRES_PROTO[p], fmt_n(a['paquetes']), fmt_n(a['bytes']),
            fmt_n(a['paquetes'] - b['paquetes']) if previa else '-',
            fmt_n(a['bytes'] - b['bytes']) if previa else '-'))
    s = m['sin_entrada']
    print(' IPv4 de flujos sin entrada en la tabla: %s paquetes, %s bytes'
          % (fmt_n(s['paquetes']), fmt_n(s['bytes'])))

    # --- flujos
    print('\nFlujos (direct counter por IP origen -> IP destino)')
    print(' %-26s %10s %12s %11s  %s' % ('Flujo', 'Paquetes', 'Bytes', 'kbit/s', 'Estado'))
    activos = 0
    for clave in sorted(m['flujos'], key=lambda k: -m['flujos'][k]['bytes']):
        f = m['flujos'][clave]
        if f['paquetes'] == 0 and not todos:
            continue
        activos += 1
        d = f['bytes'] - (previa['flujos'][clave]['bytes'] if previa else 0)
        estado = '*** ELEFANTE ***' if f['elefante'] else ''
        print(' %-26s %10s %12s %11s  %s' % (
            clave.replace('>', ' -> '), fmt_n(f['paquetes']), fmt_n(f['bytes']),
            fmt_tasa(d, dt) if previa else '-', estado))
    if activos == 0:
        print(' (sin trafico por flujos todavia; use --todos para ver todos)')

    # --- tamanos
    t = m['tamanos']
    total = sum(t['hist'])
    prom = (t['suma'] / total) if total else 0
    print('\nTamano de paquetes (registers), %s paquetes IPv4' % fmt_n(total))
    print(' ultimo: %s B   maximo: %s B   promedio: %.1f B'
          % (fmt_n(t['ultimo']), fmt_n(t['maximo']), prom))
    mayor = max(t['hist']) if total else 0
    for etiqueta, v in zip(CUBETAS, t['hist']):
        barra = '#' * int(30 * v / mayor) if mayor else ''
        print('   %-11s %10s  %s' % (etiqueta, fmt_n(v), barra))

    # --- elefantes
    ele = [k for k, f in m['flujos'].items() if f['elefante']]
    print('\nFlujos elefante (>= %s bytes acumulados): %s'
          % (fmt_n(m['umbral']),
             ', '.join(k.replace('>', ' -> ') for k in ele) if ele else 'ninguno'))
    if m['trafico_elefante']['paquetes']:
        e = m['trafico_elefante']
        print(' trafico de flujos marcados: %s paquetes, %s bytes'
              % (fmt_n(e['paquetes']), fmt_n(e['bytes'])))
    print('')
    sys.stdout.flush()


def registrar_elefantes(m, previa, ruta):
    """Escribe en un log cada flujo que se marca como elefante por primera vez."""
    nuevos = [k for k, f in m['flujos'].items()
              if f['elefante'] and not (previa and previa['flujos'][k]['elefante'])]
    for k in nuevos:
        f = m['flujos'][k]
        linea = '%s ELEFANTE %s bytes_registro=%d paquetes=%d' % (
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m['timestamp'])),
            k.replace('>', ' -> '), f['bytes_registro'], f['paquetes'])
        print('[ALERTA] nuevo flujo elefante: ' + linea)
        try: 
            with open(ruta, 'a') as fh:
                fh.write(linea + '\n')
        except OSError as e:
            print('[aviso] no se puede escribir %s (%s)' % (ruta, e))
        os.makedirs(os.path.dirname(ruta), exist_ok=True)


def main():
    ap = argparse.ArgumentParser(description='Lee los contadores de counters.p4')
    ap.add_argument('--p4info', default=os.path.join(BASE, 'build', 'counters.p4.p4info.txt'))
    ap.add_argument('--grpc', default='127.0.0.1:50051', help='servidor P4Runtime de s1')
    ap.add_argument('--device-id', type=int, default=0)
    ap.add_argument('--thrift-port', type=int, default=9090,
                    help='puerto Thrift de s1 (solo para el respaldo de registers)')
    ap.add_argument('--intervalo', type=float, default=5.0, help='segundos entre lecturas')
    ap.add_argument('--muestras', type=int, default=0, help='parar tras N lecturas (0 = sin limite)')
    ap.add_argument('--una-vez', action='store_true', help='una sola lectura')
    ap.add_argument('--umbral', type=int, help='fija el umbral de elefante (bytes) al iniciar')
    ap.add_argument('--todos', action='store_true', help='mostrar tambien flujos sin trafico')
    ap.add_argument('--snapshot', help='guarda una lectura en este JSON y termina')
    ap.add_argument('--imprimir', action='store_true', help='con --snapshot, imprime tambien la tabla')
    ap.add_argument('--log-elefantes', default=os.path.join(BASE, 'elefantes.log'))
    args = ap.parse_args()

    if not os.path.exists(args.p4info):
        sys.exit('No encuentro %s. Levante primero la red con topology.py' % args.p4info)

    sw = Switch(args)
    try:
        if args.umbral is not None:
            n = sw.fijar_umbral(args.umbral)
            print('Umbral de elefante = %s bytes en %d entradas de flujos' % (fmt_n(args.umbral), n))

        if args.snapshot:
            m = tomar_muestra(sw)
            with open(args.snapshot, 'w') as f:
                json.dump(m, f, indent=2)
            if args.imprimir:
                imprimir(m, None, 1, 0, args.todos)
            return

        previa, n = None, 0
        while True:
            m = tomar_muestra(sw)
            n += 1
            imprimir(m, previa, n, args.intervalo, args.todos)
            registrar_elefantes(m, previa, args.log_elefantes)
            previa = m
            if args.una_vez or (args.muestras and n >= args.muestras):
                break
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print('\nFin.')
    finally:
        sw.cerrar()


if __name__ == '__main__':
    main()
