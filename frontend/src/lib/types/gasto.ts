// Control de gasto (GAS2): espejo de `GET /api/v1/gasto/mensual`.
//
// Todo importe llega como **cadena** de seis decimales, no como `number`: en el
// backend es `NUMERIC(12,6)` porque es dinero que se suma miles de veces contra
// un tope, y pasarlo por un `float` de JavaScript para pintarlo devolvería el
// error que la columna existe para evitar. Se formatea al mostrar.

/**
 * Qué clase de dato es un total. No es el `usage_source` de una fila del libro
 * mayor (que solo puede ser real o estimado): sumar filas de las dos clases
 * produce un agregado que no es ni una cosa ni la otra, y quien lee la cifra
 * tiene que enterarse en el mismo sitio donde la lee.
 */
export type TotalUsageSource = "real" | "mixto" | "estimado" | "sin_datos";

/** Una fila del desglose por agente o por nodo del grafo. */
export interface SpendBreakdownRow {
  agent_role: string;
  /**
   * Nodo del grafo. `null` es el gasto que **no** está atribuido a ningún nodo
   * (los pases que no son *map*): un hueco que hay que ver, no un cero.
   */
  stage?: string | null;
  cost_usd: string;
  calls: number;
  estimated_calls: number;
}

export interface SpendTopJob {
  job_id: string;
  agent_role: string;
  cost_usd: string;
  calls: number;
}

export interface MonthlySpend {
  /** `"2026-08"`, en la zona de `timezone` y no en la del servidor. */
  month: string;
  timezone: string;
  period: { from: string; to: string };

  spent_usd: string;
  /** Objetivo. **No bloquea nunca**: es contra este número que se compara. */
  target_usd: string;
  /** Techo duro del mes. */
  cap_usd: string;
  /** Freno de una sola corrida, el que más veces actúa. */
  job_cap_usd: string;
  /** `null` cuando el tope es 0: ahí el porcentaje no existe. */
  target_pct: number | null;
  cap_pct: number | null;

  calls: number;
  input_tokens: number;
  output_tokens: number;

  estimated_calls: number;
  estimated_cost_usd: string;
  /** Fracción del **dinero** que es estimación, no de las llamadas. */
  estimated_fraction: number;
  usage_source: TotalUsageSource;

  by_agent: SpendBreakdownRow[];
  by_stage: SpendBreakdownRow[];
  top_jobs: SpendTopJob[];
}
