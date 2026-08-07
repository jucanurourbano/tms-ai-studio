"use client";

// LA MATRIZ DE AUTORIZACIÓN — la visual insignia de este artefacto, como el
// diagrama ER lo fue del modelo de datos.
//
// Se lee de un vistazo: una fila por operación, una columna por actor, y en cada
// cruce el permiso. Lo importante es que **el hueco se vea**: una celda vacía no
// significa "no aplica" sino "nadie autorizó esto", y una celda ambigua marca una
// restricción que nadie puede implementar todavía.
//
// En pantallas estrechas la tabla no se comprime hasta ser ilegible: se cambia
// por una tarjeta por operación con su lista de actores. Una matriz de 6×4 en un
// móvil es una matriz que nadie mira.

import { AlertTriangle, Ban, Check, CircleSlash, Filter } from "lucide-react";

import { IdTag, RefChip } from "@/components/artifact/primitives";
import { Badge } from "@/components/ui/badge";
import type {
  ApiAuthorizationRule,
  ApiEndpoint,
  AuthScope,
} from "@/lib/types/api";
import { cn } from "@/lib/utils";

/** Actor comodín de las denegaciones por defecto (backend: `ANY_ACTOR`). */
const ANY_ACTOR = "*";

const SCOPE_LABEL: Record<AuthScope, string> = {
  all: "todo",
  own: "solo lo suyo",
  own_team: "lo de su equipo",
  own_branch: "lo de su sede",
  custom: "criterio propio",
  none: "sin alcance",
};

const BASIS_LABEL: Record<string, string> = {
  crud_matrix: "matriz CRUD del EF",
  business_rule: "regla de negocio",
  inferred: "inferido",
  default_deny: "denegado por defecto",
};

export interface MatrixActor {
  ref: string;
  name: string;
}

/** Actores que aparecen en la matriz, en orden estable. */
export function matrixActors(rules: ApiAuthorizationRule[]): MatrixActor[] {
  const vistos = new Map<string, string>();
  for (const rule of rules) {
    if (rule.actor_ref === ANY_ACTOR) continue;
    if (!vistos.has(rule.actor_ref)) {
      vistos.set(rule.actor_ref, rule.actor_name || rule.actor_ref);
    }
  }
  return [...vistos.entries()]
    .map(([ref, name]) => ({ ref, name }))
    .sort((a, b) => a.ref.localeCompare(b.ref));
}

/** Celda: permiso de un actor sobre una operación. */
function Cell({ rule }: { rule?: ApiAuthorizationRule }) {
  if (!rule) {
    return (
      <span
        className="text-muted-foreground/40"
        title="Sin regla: este actor no puede llamar la operación"
        aria-label="sin acceso"
      >
        ·
      </span>
    );
  }
  if (rule.ambiguous) {
    return (
      <span
        className="inline-flex items-center text-amber-600"
        title={rule.note ?? "Alcance sin resolver"}
        aria-label="alcance sin resolver"
      >
        <AlertTriangle className="h-3.5 w-3.5" />
      </span>
    );
  }
  if (rule.effect === "deny") {
    return (
      <span
        className="inline-flex items-center text-red-500"
        title={rule.note ?? "Denegado"}
        aria-label="denegado"
      >
        <Ban className="h-3.5 w-3.5" />
      </span>
    );
  }
  if (rule.scope !== "all") {
    return (
      <span
        className="inline-flex items-center text-sky-600"
        title={`Acceso acotado: ${SCOPE_LABEL[rule.scope]}${
          rule.scope_expression ? ` (${rule.scope_expression})` : ""
        }`}
        aria-label={`acceso acotado: ${SCOPE_LABEL[rule.scope]}`}
      >
        <Filter className="h-3.5 w-3.5" />
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center text-emerald-600"
      title="Acceso completo"
      aria-label="acceso completo"
    >
      <Check className="h-3.5 w-3.5" />
    </span>
  );
}

export function AuthorizationMatrix({
  endpoints,
  rules,
  highlightId,
}: {
  endpoints: ApiEndpoint[];
  rules: ApiAuthorizationRule[];
  /** Id a resaltar al llegar desde un chip de referencia. */
  highlightId?: string;
}) {
  const actors = matrixActors(rules);
  const porEndpoint = new Map<string, ApiAuthorizationRule[]>();
  for (const rule of rules) {
    const lista = porEndpoint.get(rule.endpoint_ref) ?? [];
    lista.push(rule);
    porEndpoint.set(rule.endpoint_ref, lista);
  }

  const reglaDe = (endpointId: string, actorRef: string) =>
    porEndpoint.get(endpointId)?.find((r) => r.actor_ref === actorRef);

  const sinPermiso = (endpointId: string) =>
    !(porEndpoint.get(endpointId) ?? []).some((r) => r.effect === "allow");

  return (
    <div className="space-y-4">
      <Leyenda />

      {/* md+: la matriz. El scroll horizontal vive DENTRO de este contenedor. */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[36rem] text-xs">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="sticky left-0 bg-background py-1.5 pr-3 font-medium">
                Operación
              </th>
              {actors.map((actor) => (
                <th
                  key={actor.ref}
                  className="px-2 py-1.5 text-center font-medium"
                  title={actor.ref}
                >
                  {actor.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {endpoints.map((endpoint) => (
              <tr
                key={endpoint.id}
                className={cn(
                  "border-b border-border/50",
                  sinPermiso(endpoint.id) && "bg-red-50/50",
                  highlightId &&
                    (porEndpoint.get(endpoint.id) ?? []).some(
                      (r) => r.id === highlightId,
                    ) &&
                    "bg-amber-50 ring-1 ring-amber-300",
                )}
              >
                <td className="sticky left-0 bg-inherit py-1.5 pr-3">
                  <span className="flex items-center gap-1.5">
                    <MethodChip method={endpoint.method} />
                    <span className="font-mono">{endpoint.operation_id}</span>
                  </span>
                </td>
                {actors.map((actor) => (
                  <td key={actor.ref} className="px-2 py-1.5 text-center">
                    <Cell rule={reglaDe(endpoint.id, actor.ref)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Por debajo de md: una tarjeta por operación. */}
      <div className="space-y-2 md:hidden">
        {endpoints.map((endpoint) => {
          const reglas = porEndpoint.get(endpoint.id) ?? [];
          return (
            <div
              key={endpoint.id}
              className={cn(
                "rounded-lg border p-3 text-xs",
                sinPermiso(endpoint.id) && "border-red-300 bg-red-50/50",
              )}
            >
              <div className="flex items-center gap-1.5">
                <MethodChip method={endpoint.method} />
                <span className="font-mono">{endpoint.operation_id}</span>
              </div>
              <ul className="mt-2 space-y-1">
                {reglas.map((rule) => (
                  <li key={rule.id} className="flex items-start gap-2">
                    <Cell rule={rule} />
                    <span>
                      {rule.actor_ref === ANY_ACTOR
                        ? "Ningún actor"
                        : rule.actor_name || rule.actor_ref}
                      {rule.scope !== "all" && rule.effect === "allow" && (
                        <span className="text-muted-foreground">
                          {" "}
                          — {SCOPE_LABEL[rule.scope]}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      <RulesDetail rules={rules} highlightId={highlightId} />
    </div>
  );
}

function Leyenda() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <Check className="h-3 w-3 text-emerald-600" /> acceso completo
      </span>
      <span className="inline-flex items-center gap-1">
        <Filter className="h-3 w-3 text-sky-600" /> acotado por filas
      </span>
      <span className="inline-flex items-center gap-1">
        <AlertTriangle className="h-3 w-3 text-amber-600" /> alcance sin resolver
      </span>
      <span className="inline-flex items-center gap-1">
        <Ban className="h-3 w-3 text-red-500" /> denegado
      </span>
      <span className="inline-flex items-center gap-1">
        <CircleSlash className="h-3 w-3" /> sin regla
      </span>
    </div>
  );
}

/** Detalle por regla: es donde vive la trazabilidad (de dónde salió cada permiso). */
function RulesDetail({
  rules,
  highlightId,
}: {
  rules: ApiAuthorizationRule[];
  highlightId?: string;
}) {
  const acotadas = rules.filter(
    (r) => r.scope !== "all" && r.scope !== "none" && r.effect === "allow",
  );
  const denegadas = rules.filter((r) => r.effect === "deny");
  if (acotadas.length === 0 && denegadas.length === 0) return null;

  return (
    <div className="space-y-2 border-t pt-3">
      {acotadas.map((rule) => (
        <div
          key={rule.id}
          className={cn(
            "rounded-lg border p-2.5 text-xs",
            rule.ambiguous && "border-amber-300 bg-amber-50/60",
            highlightId === rule.id && "ring-1 ring-amber-400",
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <IdTag id={rule.id} />
            <span className="font-medium">
              {rule.actor_name || rule.actor_ref}
            </span>
            <Badge variant="outline">{SCOPE_LABEL[rule.scope]}</Badge>
            {rule.ambiguous && (
              <Badge
                variant="outline"
                className="border-amber-300 bg-amber-50 text-amber-700"
              >
                sin resolver
              </Badge>
            )}
            <span className="text-muted-foreground">
              {BASIS_LABEL[rule.basis] ?? rule.basis}
            </span>
          </div>
          {rule.scope_expression && (
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">
              {rule.scope_expression}
            </p>
          )}
          {rule.note && (
            <p className="mt-1 text-[11px] text-muted-foreground">{rule.note}</p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {rule.source_refs.map((ref) => (
              <RefChip key={ref} refId={ref} />
            ))}
            {rule.scope_column_refs.map((ref) => (
              <RefChip key={ref} refId={ref} />
            ))}
          </div>
        </div>
      ))}

      {denegadas.map((rule) => (
        <div
          key={rule.id}
          className={cn(
            "rounded-lg border border-red-200 bg-red-50/50 p-2.5 text-xs",
            highlightId === rule.id && "ring-1 ring-amber-400",
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <IdTag id={rule.id} />
            <Badge
              variant="outline"
              className="border-red-300 bg-red-50 text-red-700"
            >
              denegado
            </Badge>
            <span className="text-muted-foreground">
              {rule.actor_ref === ANY_ACTOR
                ? "ningún actor autorizado"
                : rule.actor_name || rule.actor_ref}
            </span>
          </div>
          {rule.note && (
            <p className="mt-1 text-[11px] text-muted-foreground">{rule.note}</p>
          )}
        </div>
      ))}
    </div>
  );
}

const METHOD_STYLE: Record<string, string> = {
  GET: "border-sky-300 bg-sky-50 text-sky-700",
  POST: "border-emerald-300 bg-emerald-50 text-emerald-700",
  PATCH: "border-amber-300 bg-amber-50 text-amber-700",
  PUT: "border-amber-300 bg-amber-50 text-amber-700",
  DELETE: "border-red-300 bg-red-50 text-red-700",
};

export function MethodChip({ method }: { method: string }) {
  return (
    <span
      className={cn(
        "inline-block rounded border px-1 py-px font-mono text-[10px] font-semibold",
        METHOD_STYLE[method] ?? "border-slate-300 bg-slate-50 text-slate-600",
      )}
    >
      {method}
    </span>
  );
}
