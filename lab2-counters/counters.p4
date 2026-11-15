/* Lab 2: Contadores y estadisticas de trafico en el plano de datos (v1model / BMv2)
 *
 * Un unico switch P4 que enruta IPv4 (LPM, TTL-1, reescritura de MAC) y,
 * ademas, mide el trafico que atraviesa el ingreso:
 *   - direct counter por flujo (IP origen + IP destino)
 *   - contadores globales por protocolo: TCP, UDP, ICMP, otros (y no IPv4)
 *   - registers con el tamano de los paquetes (ultimo, maximo, suma, histograma)
 *   - deteccion de flujos elefante: bytes acumulados por flujo contra un umbral
 *     configurable desde el plano de control
 */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

// indices del contador global por protocolo (proto_counter)
const bit<32> IDX_TCP     = 0;
const bit<32> IDX_UDP     = 1;
const bit<32> IDX_ICMP    = 2;
const bit<32> IDX_OTROS   = 3;   // IPv4 con otro protocolo
const bit<32> IDX_NO_IPV4 = 4;   // trafico que no es IPv4 (informativo)
const bit<32> NUM_PROTO   = 5;
const bit<32> NUM_CUBETAS = 5;   // histograma de tamanos (ver ingress)
const bit<32> MAX_FLUJOS  = 64;  // flujos rastreables (tamano de los registers)

// HEADERS
header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    bit<32> flow_id;     // los fija rastrear_flujo cuando el flujo esta en la tabla
    bit<64> umbral;      // umbral de bytes para considerarlo elefante
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

// PARSER
parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

// VERIFICACION CHECKSUM
control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {
        verify_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv,
              hdr.ipv4.totalLen, hdr.ipv4.identification,
              hdr.ipv4.flags, hdr.ipv4.fragOffset, hdr.ipv4.ttl,
              hdr.ipv4.protocol, hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

// INGRESS
control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    action drop() {
        mark_to_drop(standard_metadata);
    }

    // Reenvio: puerto de salida, MAC de la interfaz de salida, MAC del
    // siguiente salto y TTL-1
    action ipv4_forward(macAddr_t srcAddr, macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = srcAddr;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    table ipv4_lpm {
        key = { hdr.ipv4.dstAddr: lpm; }
        actions = { ipv4_forward; drop; }
        size = 1024;
        default_action = drop();     // sin ruta se descarta
    }

    // ---- Contadores ----------------------------------------------------

    // global por protocolo (paquetes y bytes), indexado con IDX_*
    counter(NUM_PROTO, CounterType.packets_and_bytes) proto_counter;

    // trafico IPv4 de flujos que no estan en la tabla "flujos"
    counter(1, CounterType.packets_and_bytes) flujos_sin_entrada;

    // contador directo: uno por entrada de la tabla "flujos"
    direct_counter(CounterType.packets_and_bytes) flujo_ctr;

    // El plano de control asigna un id a cada flujo y su umbral de elefante
    action rastrear_flujo(bit<32> flow_id, bit<64> umbral) {
        meta.flow_id = flow_id;
        meta.umbral  = umbral;
    }

    // Flujo = (IP origen, IP destino). Cada entrada tiene su direct counter.
    table flujos {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = { rastrear_flujo; NoAction; }
        counters = flujo_ctr;
        size = 64;
        default_action = NoAction();
    }

    // ---- Registers de tamano de paquete ----------------------------------
    // tamano = standard_metadata.packet_length (bytes, desde Ethernet)
    register<bit<64>>(NUM_CUBETAS) size_hist;  // [<=64, 65-128, 129-512, 513-1024, >1024]
    register<bit<32>>(1)           size_last;  // tamano del ultimo paquete
    register<bit<32>>(1)           size_max;   // tamano maximo visto
    register<bit<64>>(1)           size_sum;   // suma de tamanos (promedio = suma / paquetes)

    // ---- Deteccion de flujos elefante ------------------------------------
    register<bit<64>>(MAX_FLUJOS) flujo_bytes;    // bytes acumulados por flow_id
    register<bit<8>>(MAX_FLUJOS)  elefante_flag;  // 1 = flujo marcado como elefante
    counter(1, CounterType.packets_and_bytes) elefante_ctr; // trafico de flujos ya marcados

    apply {
        if (!hdr.ipv4.isValid()) {
            proto_counter.count(IDX_NO_IPV4);
            drop();                  // no es IPv4
        } else {
            // --- contador global por protocolo ---
            bit<32> idx = IDX_OTROS;
            if (hdr.ipv4.protocol == PROTO_TCP) {
                idx = IDX_TCP;
            } else if (hdr.ipv4.protocol == PROTO_UDP) {
                idx = IDX_UDP;
            } else if (hdr.ipv4.protocol == PROTO_ICMP) {
                idx = IDX_ICMP;
            }
            proto_counter.count(idx);

            // --- contador directo por flujo (se incrementa solo en un acierto) ---
            if (flujos.apply().hit) {
                // --- bytes acumulados del flujo y deteccion de elefante ---
                bit<64> acum;
                flujo_bytes.read(acum, meta.flow_id);
                acum = acum + (bit<64>) standard_metadata.packet_length;
                flujo_bytes.write(meta.flow_id, acum);

                if (acum >= meta.umbral) {
                    bit<8> marca;
                    elefante_flag.read(marca, meta.flow_id);
                    if (marca == 0) {
                        elefante_flag.write(meta.flow_id, 1);  // se marca la primera vez
                    }
                    elefante_ctr.count(0);
                }
            } else {
                flujos_sin_entrada.count(0);
            }

            // --- registers de tamano de paquete ---
            bit<32> largo = standard_metadata.packet_length;
            bit<32> cubeta = 4;
            if (largo <= 64) {
                cubeta = 0;
            } else if (largo <= 128) {
                cubeta = 1;
            } else if (largo <= 512) {
                cubeta = 2;
            } else if (largo <= 1024) {
                cubeta = 3;
            }

            bit<64> en_cubeta;
            size_hist.read(en_cubeta, cubeta);
            size_hist.write(cubeta, en_cubeta + 1);

            bit<32> maximo;
            size_max.read(maximo, 0);
            if (largo > maximo) {
                size_max.write(0, largo);
            }

            size_last.write(0, largo);

            bit<64> suma;
            size_sum.read(suma, 0);
            size_sum.write(0, suma + (bit<64>) largo);

            // --- reenvio ---
            if (hdr.ipv4.ttl <= 1) {
                drop();              // TTL agotado
            } else {
                ipv4_lpm.apply();    // sin ruta: drop por defecto
            }
        }
    }
}

// EGRESS
control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

// RECALCULO CHECKSUM
control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv,
              hdr.ipv4.totalLen, hdr.ipv4.identification,
              hdr.ipv4.flags, hdr.ipv4.fragOffset, hdr.ipv4.ttl,
              hdr.ipv4.protocol, hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

// DEPARSER
control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

// SWITCH
V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
