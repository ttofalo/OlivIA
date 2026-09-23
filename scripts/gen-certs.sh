#!/usr/bin/env bash
# Genera la CA propia del broker y un certificado de server firmado por ella.
#
# El broker MQTT no usa una CA pública: los clientes (gateway, brain, agente)
# confían en esta CA por el ca.crt. El certificado del server lleva en SAN el
# nombre interno del contenedor (mosquitto) y la IP pública del VPS, así validan
# tanto los clientes de adentro como el agente de casa.
#
#   scripts/gen-certs.sh <ip-o-host-publico> [mas-sans...]
#   scripts/gen-certs.sh 93.92.112.215
#
# Escribe en infra/mosquitto/certs/. No pisa archivos existentes salvo --force.

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)/infra/mosquitto/certs"
PUBLIC="${1:?falta la IP o el host público del VPS}"
shift || true
FORCE="${FORCE:-0}"

mkdir -p "$DIR"

if [[ -f "$DIR/server.crt" && "$FORCE" != "1" ]]; then
  echo "Ya existen certificados en $DIR. Para rehacerlos: FORCE=1 $0 $PUBLIC" >&2
  exit 1
fi

# SAN: nombre interno del contenedor, localhost y la IP/host público.
alt="DNS:mosquitto,DNS:localhost,IP:127.0.0.1"
if [[ "$PUBLIC" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  alt="$alt,IP:$PUBLIC"
else
  alt="$alt,DNS:$PUBLIC"
fi
for extra in "$@"; do
  if [[ "$extra" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    alt="$alt,IP:$extra"
  else
    alt="$alt,DNS:$extra"
  fi
done

echo "Generando CA..."
openssl genrsa -out "$DIR/ca.key" 4096 2>/dev/null
openssl req -x509 -new -nodes -key "$DIR/ca.key" -sha256 -days 3650 \
  -subj "/CN=OlivIA MQTT CA" -out "$DIR/ca.crt" 2>/dev/null

echo "Generando certificado del server con SAN: $alt"
openssl genrsa -out "$DIR/server.key" 2048 2>/dev/null
openssl req -new -key "$DIR/server.key" -subj "/CN=mosquitto" -out "$DIR/server.csr" 2>/dev/null
openssl x509 -req -in "$DIR/server.csr" -CA "$DIR/ca.crt" -CAkey "$DIR/ca.key" \
  -CAcreateserial -days 3650 -sha256 \
  -extfile <(printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth\n' "$alt") \
  -out "$DIR/server.crt" 2>/dev/null

rm -f "$DIR/server.csr" "$DIR/ca.srl"
chmod 600 "$DIR"/*.key
chmod 644 "$DIR"/*.crt

echo "Listo. Certificados en $DIR:"
ls -l "$DIR"
echo
echo "El agente de casa necesita una copia de ca.crt (no las .key)."
