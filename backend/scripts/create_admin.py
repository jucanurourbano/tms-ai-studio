"""Crea (o promueve) un usuario administrador — bootstrap del primer acceso.

Alternativa de operación al endpoint de bootstrap (``POST /auth/register`` sin
auth cuando la tabla está vacía). Útil en producción, donde puede convenir no
depender del bootstrap abierto. Es **idempotente**: si el email ya existe, se
asegura de que sea ``admin`` y esté activo (no cambia la contraseña).

Uso (desde backend/, con el venv y Postgres arriba + migración 0005 aplicada):
    .venv/bin/python scripts/create_admin.py --email admin@urbano.com.pe \
        --name "Nombre Apellido" --password "una-clave-fuerte"

Si se omite ``--password`` se solicita de forma interactiva (sin eco), para no
dejar la contraseña en el historial del shell.
"""

import argparse
import asyncio
import getpass
import os
import sys

# Permite ejecutar el archivo directamente (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password  # noqa: E402
from app.dependencies.database import session_scope  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402


async def create_admin(email: str, name: str, password: str) -> None:
    """Crea el admin o promueve el existente (idempotente)."""
    normalized = email.strip().lower()
    async with session_scope() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(normalized)
        if existing is not None:
            existing.role = UserRole.ADMIN
            existing.is_active = True
            action = "actualizado (promovido a admin/activo)"
            user_id = existing.id
        else:
            user = await repo.create(
                email=normalized,
                full_name=name.strip(),
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
            )
            action = "creado"
            user_id = user.id

    print("=" * 60)
    print(f"Administrador {action}:")
    print(f"  id:    {user_id}")
    print(f"  email: {normalized}")
    print("  Inicia sesión en el frontend: http://localhost:3000/login")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea/promueve un usuario admin.")
    parser.add_argument("--email", required=True, help="Correo del administrador.")
    parser.add_argument("--name", required=True, help="Nombre completo.")
    parser.add_argument(
        "--password",
        default=None,
        help="Contraseña (si se omite, se pide de forma interactiva).",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("Contraseña del admin: ")
    if len(password) < 8:
        parser.error("La contraseña debe tener al menos 8 caracteres.")

    asyncio.run(create_admin(args.email, args.name, password))


if __name__ == "__main__":
    main()
