#!/bin/bash
# Pruebas del Lab 2: exactitud de los contadores y deteccion de flujos elefante.
# Requiere que topology.py este corriendo en otra terminal.
# Uso: sudo bash tests/correr_pruebas.sh [fidelidad|elefante|todo]

cd "$(dirname "$0")/.." || exit 1

ESPERADO=/tmp/lab2_esperado.jsonl
ANTES=/tmp/lab2_antes.json
DESPUES=/tmp/lab2_despues.json
UMBRAL=1000000

en_host() {
    # ejecuta un comando dentro del namespace de red de un host de Mininet
    local pid
    pid=$(pgrep -f "is mininet:$1\$" | head -1)
    if [ -z "$pid" ]; then
        echo "No encontre el host $1 (esta corriendo topology.py?)"
        exit 1
    fi
    shift
    mnexec -a "$pid" "$@"
}

controlador() {
    # controller.py con el usuario que invoco sudo (tiene scapy/protobuf/grpcio)
    if [ -n "$SUDO_USER" ]; then
        sudo -u "$SUDO_USER" env "PATH=$PATH" python3 controller.py "$@"
    else
        python3 controller.py "$@"
    fi
}

generar() {
    # generar <host_origen> <ip_destino> <proto> <paquetes> <bytes_de_datos>
    en_host "$1" python3 tests/generar_trafico.py "$2" --proto "$3" \
        --count "$4" --payload "$5" --esperado "$ESPERADO"
}

probar_fidelidad() {
    echo "=== Prueba 1: los contadores reflejan el trafico inyectado ==="
    : > "$ESPERADO"
    controlador --snapshot "$ANTES" || exit 1

    generar h1 10.0.2.2 icmp 10 100     # h1 -> h2 (+ respuestas h2 -> h1)
    generar h1 10.0.3.3 udp  20 200
    generar h3 10.0.1.1 tcp  25 500
    generar h4 10.0.2.2 otros 5 50
    generar h2 10.0.3.3 udp   8 1400    # tramas de 1442 bytes (> 1024)
    sleep 1

    controlador --snapshot "$DESPUES" || exit 1
    echo
    python3 tests/verificar.py --antes "$ANTES" --despues "$DESPUES" --esperado "$ESPERADO"
    echo
}

probar_elefante() {
    echo "=== Prueba 2: deteccion de flujo elefante (umbral $UMBRAL bytes) ==="
    controlador --umbral "$UMBRAL" --snapshot "$ANTES" || exit 1

    # flujo pequeno (h1 -> h2) y flujo grande (h1 -> h4, iperf TCP 5 s)
    en_host h1 ping -c 3 -q 10.0.2.2 > /dev/null
    en_host h4 iperf -s > /tmp/lab2_iperf_servidor.txt 2>&1 &
    sleep 1
    en_host h1 iperf -c 10.0.4.4 -t 5 | tail -n 3
    pkill -f "iperf -s" 2> /dev/null
    sleep 1

    controlador --snapshot "$DESPUES" --imprimir --todos | sed -n '/Flujos (direct/,$p'
    python3 tests/verificar.py --despues "$DESPUES" \
        --elefante "10.0.1.1>10.0.4.4" --no-elefante "10.0.1.1>10.0.2.2"
    echo
    echo "Registro de elefantes (si controller.py estaba corriendo): logs/elefantes.log"
}

case "${1:-todo}" in
    fidelidad) probar_fidelidad ;;
    elefante)  probar_elefante ;;
    todo)      probar_fidelidad; probar_elefante ;;
    *) echo "Uso: $0 [fidelidad|elefante|todo]"; exit 1 ;;
esac
