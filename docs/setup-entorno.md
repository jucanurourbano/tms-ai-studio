# Setup del entorno — TMS AI Studio

Guía de reconstrucción y de trabajo diario. Entorno: **Ubuntu 24.04 LTS sobre
WSL2** con **systemd habilitado**.

---

## 1. Versiones instaladas

| Herramienta       | Versión              | Origen                          |
|-------------------|----------------------|---------------------------------|
| Ubuntu            | 24.04.1 LTS (WSL2)   | preexistente                    |
| git               | 2.43.0               | preexistente                    |
| curl              | 8.5.0                | preexistente                    |
| Python            | 3.12.3               | preexistente (satisface 3.11+)  |
| Node.js           | v24.18.0             | preexistente (satisface 20+)    |
| npm               | 11.16.0              | preexistente                    |
| build-essential   | (instalado en setup) | apt                             |
| pip               | (instalado en setup) | apt `python3-pip`               |
| venv              | (instalado en setup) | apt `python3.12-venv`           |
| Docker CE         | (instalado en setup) | repo oficial docker (nativo)    |
| Docker Compose    | (plugin v2)          | `docker-compose-plugin`         |
| gh (GitHub CLI)   | (instalado en setup) | repo oficial GitHub             |

> **Nota sobre runtimes:** ya venían Python 3.12 y Node 24, que **cumplen** los
> requisitos (3.11+ y 20+). No se reinstalaron para evitar conflictos.

### Decisión: Docker CE nativo (no Docker Desktop)

Este WSL2 corre **systemd como init** (`/etc/wsl.conf` → `systemd=true`). Por eso
se instaló **Docker CE nativo dentro de WSL2**, que:

- Arranca como servicio con `systemctl` (no depende de la GUI de Docker Desktop
  en Windows).
- Es 100% reproducible por línea de comandos (ideal para reconstrucción).
- No requiere instalar/licenciar Docker Desktop.

Docker Desktop con integración WSL sería la alternativa si no hubiera systemd o
si se prefiriera gestión desde Windows; no es el caso aquí.

---

## 2. Credenciales locales (SOLO desarrollo)

Definidas en `docker-compose.yml` y `.env` (este último **no** se versiona).

| Servicio    | Valor                                                            |
|-------------|------------------------------------------------------------------|
| PostgreSQL  | host `localhost` · puerto `5432`                                 |
| — base      | `tms_ai_studio`                                                  |
| — usuario   | `tms`                                                            |
| — password  | `tms_dev_password`                                               |
| — DATABASE_URL | `postgresql+asyncpg://tms:tms_dev_password@localhost:5432/tms_ai_studio` |
| Redis       | host `localhost` · puerto `6379` · `REDIS_URL=redis://localhost:6379/0` |

Volúmenes persistentes (los datos sobreviven a `docker compose down`):
`tms_pg_data`, `tms_redis_data`.

> Estas credenciales son de desarrollo local. **No usar en producción.**

> **⚠️ Redis Stack requerido (no Redis plano).** El checkpointer
> `langgraph-checkpoint-redis` usa comandos de **RedisJSON** (`JSON.SET` / `JSON.GET`).
> Redis plano (`redis:7`) **no** trae ese módulo y falla con
> `unknown command 'JSON.SET'`. Por eso el servicio usa la imagen
> **`redis/redis-stack-server:latest`**, que carga RedisJSON (`ReJSON`) por
> defecto. Mismo puerto `6379` y mismo volumen `tms_redis_data`.

---

## 3. Comandos de cada sesión de trabajo

### Infraestructura (contenedores)

```bash
cd ~/projects/tms-ai-studio

docker compose up -d          # levantar Postgres + Redis
docker compose ps             # ver estado / healthchecks
docker compose logs -f        # ver logs (todos)
docker compose logs -f postgres   # logs de un servicio
docker compose down           # detener (los datos persisten)
docker compose down -v        # detener y BORRAR volúmenes (¡pierde datos!)
```

### Verificaciones rápidas

```bash
# Postgres: conectar a la base
docker exec -it tms_postgres psql -U tms -d tms_ai_studio -c "\conninfo"

# Redis: ping
docker exec -it tms_redis redis-cli ping     # -> PONG

# Redis: verificar que el módulo RedisJSON está cargado (requerido por el
# checkpointer de LangGraph). Debe listar "ReJSON".
docker exec -it tms_redis redis-cli MODULE LIST

# Redis: smoke test de JSON.SET/JSON.GET (debe devolver OK y el JSON).
docker exec -it tms_redis redis-cli JSON.SET tms:smoke '$' '{"ok":true}'
docker exec -it tms_redis redis-cli JSON.GET tms:smoke
docker exec -it tms_redis redis-cli DEL tms:smoke
```

> Si `MODULE LIST` **no** muestra `ReJSON`, el contenedor está usando una imagen
> de Redis plano. Recrea el servicio con la imagen correcta:
> `docker compose up -d --force-recreate redis` (ver la nota de Redis Stack arriba).

### Backend (FastAPI)

```bash
cd ~/projects/tms-ai-studio/backend
source .venv/bin/activate

uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Probar el endpoint de salud:
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
# Docs interactivas: http://localhost:8000/docs
```

### Formato / tests

```bash
cd ~/projects/tms-ai-studio/backend
source .venv/bin/activate
black .
isort .
pytest
```

---

## 4. Reconstrucción del entorno del sistema (una sola vez)

Requiere `sudo`. Instala build-essential, pip, venv, Docker CE y gh. Ver el
script usado en la sesión de bootstrap (sección de instalación del sistema).
