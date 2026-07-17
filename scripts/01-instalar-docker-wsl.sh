#!/usr/bin/env bash
# Instala Docker CE nativo en WSL2 (Ubuntu 24.04 "noble" con systemd).
# Ejecutar con:  sudo bash scripts/01-instalar-docker-wsl.sh
set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"
echo "==> Usuario objetivo (grupo docker): ${TARGET_USER}"

echo "==> [1/6] Prerrequisitos"
apt-get update -y
apt-get install -y ca-certificates curl gnupg

echo "==> [2/6] Clave GPG oficial de Docker"
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi

echo "==> [3/6] Repositorio oficial de Docker"
CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y

echo "==> [4/6] Instalar docker-ce + compose plugin"
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> [5/6] Habilitar y arrancar el servicio (systemd)"
systemctl enable --now docker

echo "==> [6/6] Agregar ${TARGET_USER} al grupo docker"
groupadd -f docker
usermod -aG docker "${TARGET_USER}"

echo
echo "==> Versiones:"
echo "    $(docker --version)"
echo "    $(docker compose version)"
echo
echo "======================================================================"
echo " LISTO. El grupo 'docker' se aplica en una sesión NUEVA."
echo " Cierra y reabre la terminal WSL, o ejecuta:  newgrp docker"
echo " Verifica sin sudo:  docker ps"
echo "======================================================================"
