#!/usr/bin/env bash
# Bootstrap del sistema para TMS AI Studio (Ubuntu 24.04 / WSL2 con systemd).
# Instala SOLO lo que falta. Ejecutar con:  sudo bash scripts/00-bootstrap-sistema.sh
set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"
echo "==> Usuario objetivo (para grupo docker): ${TARGET_USER}"

echo "==> [1/5] apt update"
apt-get update -y

echo "==> [2/5] build-essential, pip y venv"
apt-get install -y build-essential python3-pip python3.12-venv

echo "==> [3/5] Docker CE nativo (repo oficial)"
if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
  fi
  UBUNTU_CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "    docker ya presente: $(docker --version)"
  # asegurar el plugin de compose por si faltara
  apt-get install -y docker-compose-plugin || true
fi

echo "==> [3b/5] Habilitar y arrancar el servicio docker (systemd)"
systemctl enable --now docker

echo "==> [3c/5] Agregar ${TARGET_USER} al grupo docker"
groupadd -f docker
usermod -aG docker "${TARGET_USER}"

echo "==> [4/5] GitHub CLI (gh)"
if ! command -v gh >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
  chmod a+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update -y
  apt-get install -y gh
else
  echo "    gh ya presente: $(gh --version | head -1)"
fi

echo "==> [5/5] Verificación de versiones"
echo "    gcc:            $(gcc --version | head -1)"
echo "    make:           $(make --version | head -1)"
echo "    pip:            $(pip3 --version)"
echo "    python3-venv:   OK (python3.12-venv)"
echo "    docker:         $(docker --version)"
echo "    docker compose: $(docker compose version)"
echo "    gh:             $(gh --version | head -1)"

echo
echo "======================================================================"
echo " LISTO. IMPORTANTE: el grupo 'docker' recién se aplica en una NUEVA"
echo " sesión. Cierra y reabre la terminal WSL, o ejecuta:  newgrp docker"
echo " Luego verifica SIN sudo:  docker ps"
echo "======================================================================"
