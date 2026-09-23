.PHONY: help up down logs qr discover placas venv dev-up dev-down dev-agent chat fmt test

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

up:              ## Levanta los servicios del VPS
	docker compose up -d --build

down:            ## Los baja
	docker compose down

logs:            ## Sigue los logs de todo
	docker compose logs -f

qr:              ## Muestra el QR para vincular el número del bot
	docker compose logs -f gateway

discover:        ## Inventario de red (correr en la Pi, dentro de la LAN)
	python3 scripts/discover.py

venv:            ## Crea los entornos de desarrollo (python-dvr solo va en la Pi)
	cd services/brain && python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
	cd services/agent && python3 -m venv .venv && .venv/bin/pip install -q pytest ruff paho-mqtt pyyaml structlog
	cd services/gateway && npm install

dev-up:          ## Levanta el entorno local sin hardware
	docker compose -f docker-compose.dev.yml up -d

dev-down:        ## Baja el entorno local
	docker compose -f docker-compose.dev.yml down

dev-agent:       ## Corre el agente local con cámaras falsas
	cd services/agent && AGENT_FAKE=1 MQTT_TLS=false VPS_MQTT_HOST=localhost MQTT_PORT=1883 MQTT_USER_AGENT=dev MQTT_PASS_AGENT=dev DEVICES_PATH=../../config/devices.example.yaml .venv/bin/python -m agent.main

chat:            ## Abre el chat local por MQTT
	python3 scripts/chat.py

placas:          ## Busca placas baratas para el agente en Mercado Libre y las puntúa con Jev
	cd scripts && npm install --silent && node placas_ml.mjs
	python3 scripts/rank_placas.py scripts/out/placas.json

mqtt-passwd:     ## Crea el archivo de credenciales del broker
	@test -n "$(USER_NAME)" || (echo "uso: make mqtt-passwd USER_NAME=agent" && exit 1)
	docker run --rm -it -v $(PWD)/infra/mosquitto:/m eclipse-mosquitto:2 \
		mosquitto_passwd $(shell test -f infra/mosquitto/passwd || echo -c) /m/passwd $(USER_NAME)

fmt:             ## Formatea todo
	cd services/gateway && npm run fmt
	ruff format services/brain services/agent scripts

test:            ## Corre los tests unitarios
	cd services/brain && .venv/bin/python -m pytest
	cd services/agent && .venv/bin/python -m pytest
	cd services/gateway && npm test
