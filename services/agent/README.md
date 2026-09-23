# agent

Corre en la Raspberry de casa. Es lo único que vive en la LAN.

Abre la conexión MQTT hacia el VPS y la mantiene. No escucha en ningún puerto, así que no hay nada que exponer ni que abrir en el router.

## Qué hace

- Snapshots: le pide un frame al RTSP de la cámara con ffmpeg y lo publica por MQTT.
- PTZ y presets por DVRIP en el puerto 34567, el mismo protocolo que usa la app iCSee.
- Heartbeat cada 30 segundos, para que el brain sepa que la casa está en línea.
- Más adelante, eventos de movimiento del NVR y búsqueda de grabaciones.

## Instalación en la Pi

```bash
sudo apt install -y ffmpeg python3-venv
git clone <este-repo> ~/olivia && cd ~/olivia/services/agent
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
pip install git+https://github.com/OpenIPC/python-dvr

cp ../../.env.example .env   # completar VPS_MQTT_HOST, credenciales y passwords de cámaras
sudo cp systemd/olivia-agent.service /etc/systemd/system/
sudo systemctl enable --now olivia-agent
```

## Antes de arrancar

Correr `scripts/discover.py` y llenar `config/devices.yaml`. El agente lee ese archivo y sin él no sabe a qué IP hablarle.
