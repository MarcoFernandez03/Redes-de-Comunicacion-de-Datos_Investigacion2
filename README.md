# Redes Programables con P4: Investigación y Laboratorio Base

## Curso de Redes de Computadoras. Marco Fernández Chacón - C32885 y Gabriel Coto Fernández - C4E540.

Este repositorio contiene el informe de investigación y las implementaciones P4 (sobre BMv2, con Mininet) de la tarea "Redes Programables con P4". Según el enunciado, un grupo de 2 entrega el informe, el router IPv4 estático, el sistema de contadores de tráfico y un video demostrativo. La Implementación 3 (telemetría In-Band) corresponde solo a grupos de 3 y no se incluye.

## Contenido del repositorio

| Carpeta / archivo | Contenido | 
|---|---|
| `lab1-router/` | Router IPv4 estático en P4: código P4, topología, entradas de tablas y pruebas | 
| `lab2-counters/` | Contadores y estadísticas de tráfico: código P4, controlador Python, generación de tráfico | 
| `informe/` | `informe.pdf` (investigación sobre redes programables y P4) | 
| `utils/` | Utilidades del tutorial oficial de P4 (`run_exercise.py`, `p4runtime_lib`, Makefile común) | 
| Video demostrativo | Enlace: `<ENLACE_AL_VIDEO>` | 

```text
.
├── README.md
├── .gitignore
├── utils/                  Utilidades del tutorial de P4
├── lab1-router/            Laboratorio 1: router IPv4 estático
├── lab2-counters/          Laboratorio 2: contadores y estadísticas
└── informe/                Informe de investigación
```

## Entorno y dependencias

Desarrollado y probado en la VM de Mininet con Ubuntu 20.04.1 LTS.

| Dependencia | Versión probada | Para qué se usa |
|---|---|---|
| Python 3 | 3.8.5 | Topología, generador de tablas y pruebas |
| p4c (`p4c-bm2-ss`) | 1.2.4.2 | Compila los programas P4 hacia BMv2 |
| BMv2 (`simple_switch_grpc`) | 1.15.0-68f4a978 | Switch de software que ejecuta el P4 |
| Mininet (incluye `mnexec`) | 2.3.0 | Emulación de la red |
| Scapy | 2.4.3 | Envío y captura de paquetes en las pruebas |
| protobuf (Python) | 3.6.1 | Utilidades P4Runtime |
| grpcio | 1.16.1 | Comunicación P4Runtime (gRPC) con los switches |
| psutil | 5.5.1 | Lo exigen las utilidades del Makefile al levantar la red |
| tcpdump | del sistema | Lectura de capturas en la prueba de descarte |
| iperf | 2.x | Tráfico TCP para la prueba de flujo elefante del Lab 2 |
| iptables | del sistema | Descarta respuestas del kernel de los hosts en el Lab 2 |
| Utilidades del tutorial oficial de P4 | n/a | `utils/` (`run_exercise.py`, `p4runtime_lib`) |

### Instalación

Compilador y switch P4 vía repositorio `home:p4lang` de openSUSE para Ubuntu 20.04:

```bash
echo 'deb http://download.opensuse.org/repositories/home:/p4lang/xUbuntu_20.04/ /' | sudo tee /etc/apt/sources.list.d/home:p4lang.list
curl -fsSL https://download.opensuse.org/repositories/home:p4lang/xUbuntu_20.04/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_p4lang.gpg > /dev/null
sudo apt update
sudo apt install -y p4lang-p4c p4lang-bmv2
```

Tutorial oficial, origen de `utils/`, y librerías de Python:

```bash
cd ~
git clone https://github.com/p4lang/tutorials.git
sudo apt install -y python3-pip
pip3 install --user scapy protobuf grpcio
```

`psutil` instalación con apt, porque el Makefile lo necesita al ejecutarse con `sudo`:

```bash
sudo apt install -y python3-psutil
```

Mininet y `tcpdump` vienen incluidos en la VM de Mininet.

### Obtener el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd <NOMBRE_DEL_REPOSITORIO>
```

La carpeta `utils/` ya está incluida en el repositorio con una modificación, ver "Problemas conocidos", por lo que el clon del tutorial solo es necesario si se quiere regenerarla desde el original.

---

## Laboratorio 1: Router IPv4 estático

Router IPv4 implementado en P4 y probado en Mininet con 3 routers P4 interconectados y 4 hosts en subredes distintas.

### Archivos

```text
lab1-router/
├── router.p4                   Programa P4 del router
├── topology.py                 Topología (fuente única), compila y levanta la red
├── topology.json               Generado por topology.py
├── generate_runtime.py         Genera los sX-runtime.json con las rutas
├── s1-runtime.json             Entradas estáticas de las tablas de s1
├── s2-runtime.json             Entradas estáticas de las tablas de s2
├── s3-runtime.json             Entradas estáticas de las tablas de s3
├── Makefile                    Alternativa para compilar y levantar la red
└── tests/
    ├── util.py                 Funciones comunes de las pruebas
    ├── enviar.py               Envía ICMP echo con un TTL dado
    ├── recibir.py              Captura ICMP echo y muestra TTL, MAC y checksum
    ├── traza.py                Traza de ruta con ICMP Time Exceeded
    └── correr_pruebas.sh       Pruebas de TTL, descarte sin ruta e ICMP
```

### Topología

3 routers P4 (`s1`, `s2`, `s3`) en línea y 4 hosts, cada uno en su subred:

```text
h1 ── s1 ── s2 ── s3 ── h3
            │      └─── h4
            h2
```

| Host | IP | Gateway | Router |
|---|---|---|---|
| h1 | 10.0.1.1/24 | 10.0.1.254 | s1 (puerto 1) |
| h2 | 10.0.2.2/24 | 10.0.2.254 | s2 (puerto 1) |
| h3 | 10.0.3.3/24 | 10.0.3.254 | s3 (puerto 1) |
| h4 | 10.0.4.4/24 | 10.0.4.254 | s3 (puerto 2) |

Enlaces entre routers: `s1-p2 ↔ s2-p2` y `s2-p3 ↔ s3-p3`.

Los hosts usan ARP estático hacia su gateway. El direccionamiento completo, con las MAC de cada interfaz, está en `topology.py`.

### Cómo ejecutarlo

Desde la raíz del repositorio:

```bash
cd lab1-router
sudo python3 topology.py
```

`topology.py` compila `router.p4` (genera `build/router.json` y el p4info), levanta la red en Mininet y carga las tablas de cada router por P4Runtime. Al terminar abre la CLI de Mininet; se sale con `exit`.

Alternativa con el Makefile del tutorial:

```bash
make run
```

Para regenerar las entradas de las tablas tras cambiar las rutas:

```bash
python3 generate_runtime.py
```

Si una ejecución se interrumpe y quedan procesos activos:

```bash
sudo mn -c
sudo pkill simple_switch_grpc
```

### Cómo ejecutar las pruebas

Se usan dos terminales, la red corre en la primera y los scripts de prueba en la segunda.

**Terminal 1: levantar la red y probar la conectividad**

```bash
cd lab1-router
sudo python3 topology.py
```

En la CLI de Mininet:

```text
mininet> pingall
```

Resultado esperado: `0% dropped (12/12 received)`.

**Terminal 2: pruebas automáticas**

```bash
cd lab1-router
sudo bash tests/correr_pruebas.sh
```

Sin argumentos corre todas las pruebas. También se puede elegir una: `ttl`, `sinruta` o `icmp`.

#### Prueba 1: TTL decrementado y MAC reescritas (`ttl`)

Envía 3 paquetes ICMP con TTL 64 y los captura con Scapy en el host destino. También verifica los checksums IP e ICMP del paquete recibido.

| Origen → destino | Routers que cruza | TTL esperado | MAC origen esperada |
|---|---|---|---|
| h1 → h3 | s1, s2, s3 | 61 | 08:00:00:00:03:01 |
| h1 → h2 | s1, s2 | 62 | 08:00:00:00:02:00 |
| h3 → h4 | s3 | 63 | 08:00:00:00:03:02 |

Salida esperada (h1 → h3):

```text
TTL=61  10.0.1.1 -> 10.0.3.3  | MAC 08:00:00:00:03:01 -> 08:00:00:00:03:33  | checksum IP ok, ICMP ok
```

La MAC origen es la de la interfaz de salida del último router y la destino es la del host.

#### Prueba 2: descarte sin ruta (`sinruta`)

Envía 3 paquetes a `10.0.9.9`, que no está en ninguna tabla. Como no hay un receptor para ese destino, la evidencia está en las capturas de BMv2: los paquetes entran a `s1` (`pcaps/s1-eth1_in.pcap`) y no salen por ningún puerto.

Salida esperada: 3 paquetes en `s1-eth1_in.pcap` y 0 en los archivos de salida.

#### Prueba 3: TTL agotado e ICMP Time Exceeded (`icmp`)

`traza.py` envía ICMP echo con TTL 1, 2, 3... y muestra quién responde. Además se comprueba que un paquete con TTL=1 no llega a h3.

Salida esperada de la traza h1 → h3 (cada IP es la interfaz de entrada del router):

```text
 1  10.0.1.254   Time Exceeded  (checksum IP ok, ICMP ok)
 2  10.0.12.2    Time Exceeded  (checksum IP ok, ICMP ok)
 3  10.0.23.2    Time Exceeded  (checksum IP ok, ICMP ok)
 4  10.0.3.3     Echo Reply     (checksum IP ok, ICMP ok)
```

Para el TTL=1, h3 debe reportar que no recibió ningún paquete.

---

## Laboratorio 2: Contadores y estadísticas de tráfico

Sistema de monitoreo de tráfico en el plano de datos P4, probado en Mininet con 1 switch P4 (`s1`) y 4 hosts que generan tráfico mixto. El switch enruta IPv4 y mide en el ingreso todo el tráfico que lo atraviesa. Un controlador en Python lee los contadores por P4Runtime y los imprime cada 5 segundos.

### Archivos

```text
lab2-counters/
├── counters.p4                 Programa P4: reenvío IPv4 + contadores, registers y detección de elefantes
├── topology.py                 Topología (fuente única), compila y levanta la red
├── topology.json               Generado por topology.py
├── generate_runtime.py         Genera s1-runtime.json (rutas, flujos y umbral de elefante)
├── s1-runtime.json             Entradas estáticas de las tablas de s1
├── controller.py               Controlador: lectura periódica de contadores y registers
├── Makefile                    Alternativa para compilar y levantar la red
└── tests/
    ├── util.py                 Funciones comunes
    ├── generar_trafico.py      Inyecta tráfico con Scapy (cantidad y tamaño exactos)
    ├── verificar.py            Compara los contadores contra lo inyectado
    └── correr_pruebas.sh       Pruebas de exactitud y de flujo elefante
```

### Topología

```text
h1 ──┐
h2 ──┤
     ├── s1 (switch P4)
h3 ──┤
h4 ──┘
```

| Host | IP | Gateway (interfaz de s1) | Puerto de s1 |
|---|---|---|---|
| h1 | 10.0.1.1/24 | 10.0.1.254 | 1 |
| h2 | 10.0.2.2/24 | 10.0.2.254 | 2 |
| h3 | 10.0.3.3/24 | 10.0.3.254 | 3 |
| h4 | 10.0.4.4/24 | 10.0.4.254 | 4 |

Cada host está en su propia subred con ARP estático hacia su gateway, igual que en el Lab 1. `topology.py` también desactiva IPv6 en los hosts y agrega reglas `iptables` que descartan los ICMP *destination unreachable* y los TCP *RST* que generaría el kernel del destino. Así el tráfico sintético de las pruebas no produce respuestas que se sumen a los contadores.

### Qué mide el programa P4

| Requisito | Implementación en `counters.p4` |
|---|---|
| Contadores directos por flujo (IP origen + IP destino) | Tabla `flujos` (clave exacta `srcAddr`, `dstAddr`) con `direct_counter flujo_ctr` (paquetes y bytes). Hay una entrada por cada par ordenado de hosts (12). |
| Contadores globales por protocolo | `counter proto_counter` indexado: 0 TCP, 1 UDP, 2 ICMP, 3 otros (IPv4 con otro protocolo), 4 no IPv4 (informativo). |
| Tamaño de los paquetes con registers | `size_last` (último), `size_max` (máximo), `size_sum` (suma, para el promedio) y `size_hist`, un histograma de 5 cubetas: ≤64, 65-128, 129-512, 513-1024 y >1024 bytes. |
| Detección de flujo elefante | `flujo_bytes` acumula bytes por flujo. Al llegar al umbral se marca `elefante_flag` (1) y el tráfico posterior de ese flujo se cuenta en `elefante_ctr`. El umbral es un parámetro de la acción `rastrear_flujo`, configurable desde el plano de control. |

Detalles de medición:

- Se cuenta en el **ingreso**, antes de decidir el reenvío: un paquete descartado (TTL agotado o sin ruta) también queda contado, porque llegó al switch.
- El tamaño es `standard_metadata.packet_length`: bytes de la trama desde la cabecera Ethernet (sin FCS). Los contadores de bytes de BMv2 usan esa misma medida.
- Los paquetes IPv4 cuyo par origen-destino no está en la tabla `flujos` se cuentan en `flujos_sin_entrada` (pero sí en el contador por protocolo).
- Un mismo paquete se ve una vez por el contador global y una vez por el contador de su flujo; un ping genera dos flujos (solicitud y respuesta).

### Cómo ejecutarlo

Se usan tres terminales. Todos los comandos parten de la raíz del repositorio.

**Terminal 1: levantar la red**

```bash
cd lab2-counters
sudo python3 topology.py
```

Compila `counters.p4` (genera `build/counters.json` y el p4info), levanta la red en Mininet y carga las tablas de `s1` por P4Runtime. Al terminar abre la CLI de Mininet. Para comprobar la conectividad:

```text
mininet> pingall
```

Resultado esperado: `0% dropped (12/12 received)`.

Alternativa con el Makefile del tutorial: `make run`.

**Terminal 2: controlador (lectura periódica)**

```bash
cd lab2-counters
python3 controller.py                  # imprime cada 5 s
```

Opciones útiles:

| Opción | Efecto |
|---|---|
| `--intervalo 2` | Segundos entre lecturas (5 por defecto) |
| `--umbral 500000` | Cambia en caliente el umbral de flujo elefante (bytes) en las 12 entradas |
| `--todos` | Muestra también los flujos sin tráfico |
| `--una-vez` | Una sola lectura |
| `--snapshot a.json` | Guarda una lectura en JSON y termina (la usan las pruebas) |
| `--muestras N` | Termina tras N lecturas |

Cada lectura muestra: contadores por protocolo con los incrementos desde la lectura anterior, la tabla de flujos con paquetes, bytes y tasa (kbit/s), el tamaño de paquetes (último, máximo, promedio e histograma) y los flujos elefante. Cada flujo que se marca por primera vez produce una alerta y una línea en `logs/elefantes.log`.

Para generar el tráfico a mano desde la CLI de Mininet (Terminal 1):

```text
mininet> h1 ping -c 5 h2
mininet> h1 python3 tests/generar_trafico.py 10.0.3.3 --proto udp --count 50 --payload 300
mininet> h4 iperf -s &
mininet> h1 iperf -c 10.0.4.4 -t 10
```

**Terminal 3: pruebas automáticas**

```bash
cd lab2-counters
sudo bash tests/correr_pruebas.sh        # todas
sudo bash tests/correr_pruebas.sh fidelidad
sudo bash tests/correr_pruebas.sh elefante
```

#### Prueba 1: los contadores reflejan el tráfico inyectado (`fidelidad`)

Toma una lectura (`--snapshot`) antes y otra después de inyectar tráfico conocido, y `verificar.py` compara las diferencias:

| Origen → destino | Protocolo | Paquetes | Bytes de datos | Trama Ethernet |
|---|---|---|---|---|
| h1 → h2 | ICMP echo | 10 (más 10 respuestas h2 → h1) | 100 | 142 B |
| h1 → h3 | UDP | 20 | 200 | 242 B |
| h3 → h1 | TCP | 25 | 500 | 554 B |
| h4 → h2 | IP proto 253 (otros) | 5 | 50 | 84 B |
| h2 → h3 | UDP | 8 | 1400 | 1442 B |

Compara por flujo (paquetes y bytes), por protocolo, el histograma de tamaños y que el tamaño máximo sea al menos 1442 B. Salida esperada al final: `RESULTADO: TODO CORRECTO`.

#### Prueba 2: detección de flujo elefante (`elefante`)

Fija el umbral en 1 000 000 de bytes (`controller.py --umbral`), envía 3 pings h1 → h2 (flujo pequeño) y un `iperf` TCP de 5 s h1 → h4 (flujo grande). Espera que `10.0.1.1 -> 10.0.4.4` quede marcado como elefante y `10.0.1.1 -> 10.0.2.2` no. La marca y los bytes acumulados se leen de los registers.

Si el controlador está corriendo en la Terminal 2 durante esta prueba, verá la alerta de nuevo flujo elefante y se escribe en `logs/elefantes.log`.

### Notas y limitaciones

- Los contadores y registers acumulan desde que arranca la red. Para empezar de cero, salir de Mininet (`exit`) y volver a ejecutar `topology.py`. La prueba de fidelidad usa diferencias entre dos lecturas, así que no necesita reiniciar. Los flujos elefante quedan marcados hasta reiniciar.
- La prueba de fidelidad espera exactitud. Cualquier tráfico IPv4 extra de los hosts durante la prueba (por ejemplo un `ping` manual en paralelo) hará que `verificar.py` reporte diferencias.
- Los registers se leen por P4Runtime. Si esa lectura falla, `controller.py` avisa y usa el cliente Thrift de BMv2 (`simple_switch_CLI --thrift-port 9090`).
- Las reglas `iptables` de los hosts requieren que `iptables` esté instalado en la VM (viene con Ubuntu).
- `iperf` (versión 2) debe estar instalado: `sudo apt install -y iperf`.

## Informe de investigación y video

TODO

---

## Problemas conocidos

- `utils/p4runtime_lib/helper.py` se modificó para quitar el argumento `allow_unknown_field=True` de la llamada a `text_format.Merge`. La VM usa protobuf 3.6.1 (Ubuntu 20.04), que no lo soporta.
- El `Makefile` y `topology.py` generan el p4info como `build/router.p4.p4info.txt` y los `sX-runtime.json` deben apuntar a ese nombre (lo hace `generate_runtime.py`).
