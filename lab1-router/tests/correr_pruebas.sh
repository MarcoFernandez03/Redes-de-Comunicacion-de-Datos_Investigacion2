#!/bin/bash
# Pruebas del Lab 1: TTL, MAC, descarte sin ruta e ICMP Time Exceeded.
# Requiere que topology.py esté corriendo en otra terminal.
# Uso: sudo bash tests/correr_pruebas.sh [ttl|sinruta|icmp|todo]

cd "$(dirname "$0")/.." || exit 1

en_host() {
    # ejecuta un comando dentro del namespace de red de un host de Mininet
    local pid
    pid=$(pgrep -f "is mininet:$1\$" | head -1)
    if [ -z "$pid" ]; then
        echo "No encontré el host $1 (¿está corriendo topology.py?)"
        exit 1
    fi
    shift
    mnexec -a "$pid" "$@"
}

esperar_receptor() {
    # espera a que recibir.py ya esté escuchando
    for i in $(seq 20); do
        grep -q Escuchando "$1" 2>/dev/null && break
        sleep 0.5
    done
    sleep 0.5
}

probar_ttl() {
    # probar_ttl <origen> <destino> <ip_destino> <ttl_esperado>
    echo "--- $1 -> $2 ($3): TTL esperado $4"
    : > "/tmp/recibido_$2.txt"
    en_host "$2" python3 tests/recibir.py --count 3 --timeout 8 > "/tmp/recibido_$2.txt" 2>&1 &
    esperar_receptor "/tmp/recibido_$2.txt"
    en_host "$1" python3 tests/enviar.py "$3" --count 3
    wait
    cat "/tmp/recibido_$2.txt"
    echo
}

probar_sin_ruta() {
    echo "--- h1 -> 10.0.9.9 (sin ruta): debe descartarse en s1"
    en_host h1 python3 tests/enviar.py 10.0.9.9 --count 3
    sleep 2
    echo "Paquetes con destino 10.0.9.9 en las capturas de s1:"
    for f in pcaps/s1-eth*.pcap; do
        n=$(tcpdump -nn -r "$f" 2>/dev/null | grep -c 10.0.9.9)
        echo "  $f: $n"
    done
    echo "(esperado: solo el archivo de entrada de h1 tiene paquetes, los de salida 0)"
    echo
}

probar_icmp() {
    echo "--- traza h1 -> h3 (ICMP Time Exceeded)"
    en_host h1 python3 tests/traza.py 10.0.3.3
    echo
    echo "--- h1 -> h3 con TTL=1: no debe llegar a h3"
    : > /tmp/recibido_h3.txt
    en_host h3 python3 tests/recibir.py --count 1 --timeout 5 > /tmp/recibido_h3.txt 2>&1 &
    esperar_receptor /tmp/recibido_h3.txt
    en_host h1 python3 tests/enviar.py 10.0.3.3 --ttl 1 --count 2
    wait
    cat /tmp/recibido_h3.txt
    echo
}

case "${1:-todo}" in
    ttl)
        probar_ttl h1 h3 10.0.3.3 61
        probar_ttl h1 h2 10.0.2.2 62
        probar_ttl h3 h4 10.0.4.4 63
        ;;
    sinruta) probar_sin_ruta ;;
    icmp)    probar_icmp ;;
    todo)
        probar_ttl h1 h3 10.0.3.3 61
        probar_ttl h1 h2 10.0.2.2 62
        probar_ttl h3 h4 10.0.4.4 63
        probar_sin_ruta
        probar_icmp
        ;;
    *) echo "Uso: sudo bash tests/correr_pruebas.sh [ttl|sinruta|icmp|todo]" ;;
esac
