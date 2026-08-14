"""Restablece la contraseña de un usuario por CLI — recuperación de acceso.

Hermano de ``create_admin.py``, que es idempotente pero **no** toca la contraseña
del usuario existente. Existe para el caso sin salida del endpoint
``POST /auth/users/{id}/password``: ese exige ``config`` FULL, es decir un token,
y quien no puede iniciar sesión no tiene token. Este script rompe ese círculo
desde el servidor, donde ya se tiene acceso a la base de datos.

La contraseña **siempre** se pide de forma interactiva y sin eco: no se acepta por
argumento para que no quede en el historial del shell ni en la lista de procesos,
y solo se persiste su hash (nunca se registra en claro, igual que en la API).

Uso (desde backend/, con el venv y Postgres arriba):
    .venv/bin/python scripts/reset_password.py --email jnunez@urbano.com.pe
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
from app.repositories.user_repository import UserRepository  # noqa: E402

MIN_LENGTH = 8  # Mismo mínimo que los esquemas de la API (app/schemas/auth.py).


async def reset_password(email: str, password: str, *, reactivate: bool) -> None:
    """Reemplaza el hash de contraseña del usuario indicado."""
    normalized = email.strip().lower()
    async with session_scope() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email(normalized)
        if user is None:
            print(f"ERROR: no existe ningún usuario con el correo {normalized}.")
            print("Los correos se guardan en minúsculas; revisa que sea el correcto.")
            raise SystemExit(1)

        # Un usuario dado de baja o desactivado no inicia sesión por diseño: sin
        # esto el reseteo dejaría la contraseña nueva y el acceso igual de cerrado.
        blocked = []
        if not user.is_active:
            blocked.append("desactivado")
        if user.deleted_at is not None:
            blocked.append("dado de baja")
        if blocked and not reactivate:
            print(f"ERROR: el usuario está {' y '.join(blocked)} y no podrá entrar.")
            print("Vuelve a ejecutar con --reactivar para restablecer y reactivar.")
            raise SystemExit(1)

        await repo.set_password_hash(user, hash_password(password))
        if blocked:
            user.is_active = True
            user.deleted_at = None

    print("=" * 60)
    print("Contraseña restablecida:")
    print(f"  id:    {user.id}")
    print(f"  email: {normalized}")
    print(f"  rol:   {user.role.value}")
    if blocked:
        print(f"  Se reactivó la cuenta (estaba {' y '.join(blocked)}).")
    print("  Inicia sesión en el frontend: http://localhost:3000/login")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restablece la contraseña de un usuario (la pide sin eco)."
    )
    parser.add_argument("--email", required=True, help="Correo de acceso del usuario.")
    parser.add_argument(
        "--reactivar",
        dest="reactivate",
        action="store_true",
        help="Reactiva la cuenta si está desactivada o dada de baja.",
    )
    args = parser.parse_args()

    password = getpass.getpass("Contraseña nueva: ")
    if len(password) < MIN_LENGTH:
        parser.error(f"La contraseña debe tener al menos {MIN_LENGTH} caracteres.")
    if password != getpass.getpass("Repite la contraseña nueva: "):
        parser.error("Las contraseñas no coinciden.")

    asyncio.run(reset_password(args.email, password, reactivate=args.reactivate))


if __name__ == "__main__":
    main()
