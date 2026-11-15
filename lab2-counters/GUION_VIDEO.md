# Guion del video: Lab 2 (aprox. 2 a 2:30 min, parte del máximo de 5 min)

Preparar 3 terminales visibles a la vez (Terminal 1: red, 2: controlador, 3: pruebas).

1. **(0:00) Qué se hizo.** Mostrar `counters.p4` y señalar: tabla `flujos` con `direct_counter`, `proto_counter`, registers `size_*` y `flujo_bytes`/`elefante_flag`.
2. **(0:30) Levantar la red.** Terminal 1: `sudo python3 topology.py`, luego `pingall` (0% dropped).
3. **(0:50) Controlador.** Terminal 2: `python3 controller.py`. Mostrar que imprime cada 5 s (todo en cero o con el pingall).
4. **(1:10) Exactitud.** Terminal 3: `sudo bash tests/correr_pruebas.sh fidelidad`. Mostrar la tabla con `esperado` = `obtenido` y `TODO CORRECTO`. Volver a la Terminal 2 y mostrar que los contadores subieron (protocolos, flujos, histograma).
5. **(2:00) Flujo elefante.** Terminal 3: `sudo bash tests/correr_pruebas.sh elefante`. Mostrar en la Terminal 2 la alerta `nuevo flujo elefante 10.0.1.1 -> 10.0.4.4` y la marca `*** ELEFANTE ***`.
6. **(2:30) Umbral en caliente (opcional).** `python3 controller.py --umbral 50000 --una-vez`, generar un UDP de unos 100 KB y mostrar el nuevo flujo marcado.
7. **Cierre.** Mencionar `README.md` con las instrucciones y `logs/elefantes.log`.
