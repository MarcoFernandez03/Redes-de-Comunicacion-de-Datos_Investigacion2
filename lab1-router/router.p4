/* Router IPv4 estátic
 * Parsing Ethernet/IPv4, LPM, decremento de TTL,
 * reescritura de MAC origen/destino, drop por defecto y por TTL agotado.
 * Respuesta ICMP Time Exceeded cuando se agota el TTL.
 */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  ICMP_TIME_EXCEEDED = 11;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

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

// primeros 8 bytes de la carga del paquete original (para el ICMP)
header l4_head_t {
    bit<64> data;
}

header icmp_t {
    bit<8>  type;
    bit<8>  code;
    bit<16> checksum;
    bit<32> unused;
}

struct metadata {
    ip4Addr_t icmp_src;      // IP del router usada como origen del ICMP
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    l4_head_t  l4_head;
    icmp_t     icmp;
    ipv4_t     inner_ipv4;
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
        transition select(hdr.ipv4.ttl) {
            0: parse_l4_head;    // TTL agotado, se necesitan los 8 bytes
            1: parse_l4_head;
            default: accept;
        }
    }

    state parse_l4_head {
        packet.extract(hdr.l4_head);
        transition accept;
    }
}

// VERFICACION CHECKSUM
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

    // Reenví con puerto de salida, MAC destino del siguiente salto, TTL-1
    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    table ipv4_lpm {
        key = { hdr.ipv4.dstAddr: lpm; }
        actions = { ipv4_forward; drop; }
        size = 1024;
        default_action = drop();     // sin ruta se descarta
    }

    // IP de la interfaz de entrada, origen del ICMP
    action set_icmp_src(ip4Addr_t ip) {
        meta.icmp_src = ip;
    }

    table icmp_src {
        key = { standard_metadata.ingress_port: exact; }
        actions = { set_icmp_src; NoAction; }
        size = 16;
        default_action = NoAction();
    }

    // Convierte el paquete en un ICMP Time Exceeded hacia el origen
    // la MAC y el puerto de salida los pone ipv4_lpm y egress_mac
    action build_time_exceeded() {
        // guarda el datagrama original (IPv4 + 8 bytes de carga)
        hdr.inner_ipv4 = hdr.ipv4;

        // cabecera ICMP, el checksum se calcula en MyComputeChecksum
        hdr.icmp.setValid();
        hdr.icmp.type     = ICMP_TIME_EXCEEDED;
        hdr.icmp.code     = 0;
        hdr.icmp.checksum = 0;
        hdr.icmp.unused   = 0;

        // nuevo IPv4 externo: 20 (IP) + 8 (ICMP) + 20 (IP orig) + 8 (carga)
        hdr.ipv4.version        = 4;
        hdr.ipv4.ihl            = 5;
        hdr.ipv4.diffserv       = 0;
        hdr.ipv4.totalLen       = 56;
        hdr.ipv4.identification = 0;
        hdr.ipv4.flags          = 0;
        hdr.ipv4.fragOffset     = 0;
        hdr.ipv4.ttl            = 64;
        hdr.ipv4.protocol       = PROTO_ICMP;
        hdr.ipv4.srcAddr        = meta.icmp_src;
        hdr.ipv4.dstAddr        = hdr.inner_ipv4.srcAddr;
    }

    apply {
        if (!hdr.ipv4.isValid()) {
            drop();                  // no es IPv4
        } else if (hdr.ipv4.ttl <= 1 && !hdr.l4_head.isValid()) {
            drop();                  // TTL agotado y sin datos para el ICMP
        } else {
            if (hdr.ipv4.ttl <= 1) {
                icmp_src.apply();
                build_time_exceeded();   // TTL agotado, se responde ICMP
            }
            ipv4_lpm.apply();        // reenvío normal o ruta de regreso del ICMP
        }
    }
}

// EGRESS
control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    // MAC origen = MAC de la interfaz por la que sale el paquete
    action set_src_mac(macAddr_t srcAddr) {
        hdr.ethernet.srcAddr = srcAddr;
    }

    table egress_mac {
        key = { standard_metadata.egress_port: exact; }
        actions = { set_src_mac; NoAction; }
        size = 16;
        default_action = NoAction();
    }

    apply {
        if (hdr.ipv4.isValid()) {
            egress_mac.apply();
        }
    }
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

        // checksum del ICMP: cabecera + IPv4 original + 8 bytes de carga
        update_checksum(
            hdr.icmp.isValid(),
            { hdr.icmp.type, hdr.icmp.code, 16w0, hdr.icmp.unused,
              hdr.inner_ipv4.version, hdr.inner_ipv4.ihl,
              hdr.inner_ipv4.diffserv, hdr.inner_ipv4.totalLen,
              hdr.inner_ipv4.identification, hdr.inner_ipv4.flags,
              hdr.inner_ipv4.fragOffset, hdr.inner_ipv4.ttl,
              hdr.inner_ipv4.protocol, hdr.inner_ipv4.hdrChecksum,
              hdr.inner_ipv4.srcAddr, hdr.inner_ipv4.dstAddr,
              hdr.l4_head.data },
            hdr.icmp.checksum,
            HashAlgorithm.csum16);
    }
}

// DEPARSER
control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.icmp);
        packet.emit(hdr.inner_ipv4);
        packet.emit(hdr.l4_head);
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
