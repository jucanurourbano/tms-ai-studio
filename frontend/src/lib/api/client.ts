// Cliente HTTP tipado. Maneja el envelope ApiResponse {success,message,data}
// en un solo lugar: desempaqueta `data` o lanza ApiError con el mensaje.

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, init);
  } catch {
    throw new ApiError(
      "No se pudo conectar con el backend. ¿Está corriendo en " +
        `${API_BASE}?`,
      0,
    );
  }

  let body: ApiResponse<T> | null = null;
  try {
    body = (await res.json()) as ApiResponse<T>;
  } catch {
    body = null;
  }

  if (!res.ok || !body || body.success === false) {
    const message = body?.message ?? `Error HTTP ${res.status}`;
    const code =
      body?.data && typeof body.data === "object"
        ? (body.data as Record<string, unknown>).code
        : undefined;
    throw new ApiError(message, res.status, code as string | undefined);
  }

  return body.data as T;
}
