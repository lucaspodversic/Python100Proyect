# 92 · Análisis de tráfico de red con Scapy

Herramienta de línea de comandos que lee un archivo **pcap/pcapng**, o captura en vivo en una **interfaz propia**, y muestra estadísticas de tráfico:

- por protocolo;
- por IP de origen y de destino;
- por puerto de servicio;
- por conversación;
- tasa media y pico de tráfico.

## Qué demuestra

- **Streaming**: `PcapReader` itera los paquetes sin cargar el archivo entero, y `Estadisticas` acumula en `Counter`s.
- **Clasificación** de TCP, UDP, ICMP, ICMPv6, ARP, IPv4 e IPv6. Se toma el puerto de servicio (el menor del par) y se le pone nombre (443 → https, 53 → dns).
- **Seudonimización** opcional de IPs con HMAC-SHA256 y una clave aleatoria por ejecución, para compartir un informe sin exponer direcciones.
- **Captura en vivo con salvaguardas**:
  - La interfaz es obligatoria y debe existir localmente.
  - El modo promiscuo está desactivado.
  - Se puede usar un filtro BPF.
  - Si faltan permisos, el mensaje es claro.
- Salida en tabla de texto o JSON.

## Uso responsable ⚠️

La captura en vivo es solo para **equipos y redes propios o con autorización por escrito**. Interceptar comunicaciones ajenas es delito en la mayoría de las jurisdicciones. La herramienta no incluye modo monitor wifi, envenenamiento ARP ni nada que permita ver tráfico de terceros.

## Arquitectura

```
trafico/
├── analisis.py  # clasificar(paquete), Estadisticas (acumulador, seudonimización, tasas)
├── fuentes.py   # leer_pcap (streaming), interfaces(), capturar_vivo (validaciones + permisos)
├── informe.py   # a_texto, a_json, humano(bytes)
└── cli.py       # subcomandos pcap | vivo | interfaces
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m trafico pcap captura.pcap --top 5
python -m trafico pcap captura.pcap --json --seudonimizar > informe.json
python -m trafico interfaces
sudo .venv/bin/python -m trafico vivo --interfaz eth0 --paquetes 200 --filtro "tcp port 443"
```

- Para no usar `sudo` en Linux: `sudo setcap cap_net_raw,cap_net_admin=eip $(readlink -f .venv/bin/python)`.
- En Windows hace falta Npcap.

## Tests

```bash
pytest
```

- El `conftest.py` **genera un pcap sintético** con `wrpcap`, con TCP/443, DNS, ICMP, ARP e ICMPv6. Nunca se captura tráfico real.
- La captura en vivo solo se prueba en sus validaciones: interfaz desconocida, rango de paquetes y falta de permisos (simulada con `monkeypatch`).

## Limitaciones

- Los conteos de puerto asumen que el puerto de servicio es el menor; falla con servicios en puertos altos entre sí.
- No reensambla flujos ni inspecciona contenido (DPI): TLS está cifrado y así debe quedar.
- La captura en vivo guarda los paquetes en memoria (`store=True`); para capturas largas, usá `tcpdump -w` y analizá el pcap.
- No hay métricas de latencia ni de retransmisiones TCP.
