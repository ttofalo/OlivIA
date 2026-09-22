.PHONY: help up down logs qr discover fmt

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

mqtt-passwd:     ## Crea el archivo de credenciales del broker
	@test -n "$(USER_NAME)" || (echo "uso: make mqtt-passwd USER_NAME=agent" && exit 1)
	docker run --rm -it -v $(PWD)/infra/mosquitto:/m eclipse-mosquitto:2 \
		mosquitto_passwd $(shell test -f infra/mosquitto/passwd || echo -c) /m/passwd $(USER_NAME)

fmt:             ## Formatea todo
	cd services/gateway && npm run fmt
	ruff format services/brain services/agent scripts
