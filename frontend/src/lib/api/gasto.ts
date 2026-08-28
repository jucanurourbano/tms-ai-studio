// Control de gasto (GAS2). Solo lectura: el freno vive en el backend y corre
// antes de cada llamada al modelo; esto es la ventana por la que se ve.

import type { MonthlySpend } from "@/lib/types/gasto";

import { apiRequest } from "./client";

export const gastoApi = {
  monthly(): Promise<MonthlySpend> {
    return apiRequest<MonthlySpend>("/gasto/mensual");
  },
};
