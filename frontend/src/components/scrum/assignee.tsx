"use client";

import { UserPlus, Users } from "lucide-react";

import { fairShare, isOverloaded, type MemberLoad } from "@/lib/scrum-assignments";
import { SPECIALTY_LABELS } from "@/lib/permissions";
import { NativeSelect } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";
import type { TeamMember } from "@/lib/types/scrum";

/** Iniciales del colaborador (máximo dos), para el avatar. */
export function initialsOf(fullName: string): string {
  return (
    fullName
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p.charAt(0).toUpperCase())
      .join("") || "?"
  );
}

/** Avatar circular con iniciales. Tamaño `sm` para tablas, `md` para fichas. */
export function AssigneeAvatar({
  member,
  size = "sm",
  className,
}: {
  member: TeamMember;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <span
      title={`${member.full_name}${member.specialty ? ` · ${SPECIALTY_LABELS[member.specialty]}` : ""}`}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-primary/10 font-semibold text-primary ring-1 ring-primary/20",
        size === "sm" ? "h-5 w-5 text-[9px]" : "h-7 w-7 text-[11px]",
        className,
      )}
    >
      {initialsOf(member.full_name)}
    </span>
  );
}

/**
 * Badge del responsable de una historia: avatar + nombre (+ especialidad).
 * En espacios estrechos (`compact`) se muestra solo el avatar con tooltip.
 */
export function AssigneeBadge({
  member,
  compact = false,
  inherited = false,
}: {
  member?: TeamMember | null;
  compact?: boolean;
  /** Heredado del sprint: se muestra atenuado para no confundirlo con lo explícito. */
  inherited?: boolean;
}) {
  if (!member) {
    return <span className="text-[11px] text-meta-foreground">sin asignar</span>;
  }
  if (compact) return <AssigneeAvatar member={member} />;
  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5",
        inherited && "opacity-70",
      )}
      title={inherited ? "Heredado del responsable del sprint" : undefined}
    >
      <AssigneeAvatar member={member} />
      <span className="min-w-0 truncate text-xs">{member.full_name}</span>
      {member.specialty && (
        <span className="shrink-0 text-[11px] text-meta-foreground">
          · {SPECIALTY_LABELS[member.specialty]}
        </span>
      )}
    </span>
  );
}

/**
 * Selector "Asignar a" de una historia.
 *
 * Es un `<select>` nativo a propósito: la lista de colaboradores es corta, el
 * teclado y el móvil lo manejan mejor que un menú propio, y aparece repetido en
 * cada fila del plan (un popover por fila sería mucho más costoso). El avatar y
 * la especialidad se muestran al lado, ya que un `<option>` no admite marcado.
 *
 * En modo lectura (`readOnly`) no se renderiza el control: solo el badge.
 */
export function AssigneeSelect({
  storyId,
  team,
  member,
  inherited = false,
  readOnly = false,
  busy = false,
  onAssign,
}: {
  storyId: string;
  team: TeamMember[];
  member?: TeamMember | null;
  /** El responsable viene heredado del sprint, no de esta historia. */
  inherited?: boolean;
  readOnly?: boolean;
  busy?: boolean;
  onAssign: (storyId: string, userId: string | null) => void;
}) {
  if (readOnly) return <AssigneeBadge member={member} inherited={inherited} />;

  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      {member ? (
        <AssigneeAvatar member={member} />
      ) : (
        <UserPlus className="h-3.5 w-3.5 shrink-0 text-meta-foreground" />
      )}
      <NativeSelect
        aria-label={`Asignar la historia ${storyId}`}
        value={inherited ? "" : (member?.id ?? "")}
        disabled={busy}
        onChange={(e) => onAssign(storyId, e.target.value || null)}
        className="h-8 min-w-0 max-w-[11rem] text-xs"
      >
        <option value="">
          {inherited && member
            ? `Hereda del sprint (${member.full_name})`
            : "Sin asignar"}
        </option>
        {team.map((m) => (
          <option key={m.id} value={m.id}>
            {m.full_name}
            {m.specialty ? ` — ${SPECIALTY_LABELS[m.specialty]}` : ""}
          </option>
        ))}
      </NativeSelect>
    </span>
  );
}

/**
 * Carga por colaborador dentro de un sprint, para detectar **sobrecarga** de un
 * vistazo: se marca en ámbar a quien supera el reparto equitativo de la
 * capacidad del sprint (capacidad ÷ personas con historias), que es la señal
 * barata y explicable — no hay capacidad individual declarada por persona.
 */
export function SprintLoad({
  loads,
  capacityPoints,
  unassignedPoints,
}: {
  loads: MemberLoad[];
  capacityPoints: number;
  unassignedPoints: number;
}) {
  if (loads.length === 0 && unassignedPoints === 0) return null;

  const reparto = fairShare(capacityPoints, loads.length);

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] text-meta-foreground">Carga:</span>
      {loads.map(({ member, stories, points }) => {
        const sobrecargado = isOverloaded(points, reparto);
        return (
          <span
            key={member.id}
            title={
              sobrecargado
                ? `${member.full_name}: ${points} pts en ${stories} historia(s) — por encima del reparto equitativo (${reparto.toFixed(1)} pts)`
                : `${member.full_name}: ${points} pts en ${stories} historia(s)`
            }
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-1.5 py-0.5 text-[11px]",
              sobrecargado
                ? "border-amber-300 bg-amber-50 text-amber-800"
                : "border-border bg-muted/40 text-muted-foreground",
            )}
          >
            <AssigneeAvatar member={member} />
            <span className="max-w-[8rem] truncate">{member.full_name}</span>
            <span className="font-mono tabular-nums">{points} pts</span>
            {sobrecargado && <span aria-hidden>⚠</span>}
          </span>
        );
      })}
      {unassignedPoints > 0 && (
        <span
          title="Puntos del sprint en historias sin responsable"
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-1.5 py-0.5 text-[11px] text-meta-foreground"
        >
          sin asignar
          <span className="font-mono tabular-nums">{unassignedPoints} pts</span>
        </span>
      )}
    </div>
  );
}


/**
 * Selector "Asignar sprint a…" para la cabecera de un sprint.
 *
 * Asignar el sprint hace que TODAS sus historias sin responsable propio pasen a
 * mostrarse a nombre de esa persona. Es la vía rápida del caso habitual ("este
 * sprint lo lleva Ana"), y las excepciones se siguen marcando historia a historia.
 */
export function SprintAssigneeSelect({
  sprintId,
  team,
  member,
  readOnly = false,
  busy = false,
  onAssign,
}: {
  sprintId: string;
  team: TeamMember[];
  member?: TeamMember | null;
  readOnly?: boolean;
  busy?: boolean;
  onAssign: (sprintId: string, userId: string | null) => void;
}) {
  if (readOnly) {
    return member ? (
      <span className="inline-flex items-center gap-1.5">
        <span className="text-[11px] text-meta-foreground">Responsable:</span>
        <AssigneeBadge member={member} />
      </span>
    ) : null;
  }

  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 print:hidden">
      {member ? (
        <AssigneeAvatar member={member} />
      ) : (
        <Users className="h-3.5 w-3.5 shrink-0 text-meta-foreground" />
      )}
      <NativeSelect
        aria-label={`Asignar el sprint ${sprintId}`}
        value={member?.id ?? ""}
        disabled={busy}
        onChange={(e) => onAssign(sprintId, e.target.value || null)}
        title="Asigna el sprint completo: sus historias sin responsable propio pasarán a esta persona"
        className="h-8 min-w-0 max-w-[13rem] text-xs"
      >
        <option value="">Asignar sprint a…</option>
        {team.map((m) => (
          <option key={m.id} value={m.id}>
            {m.full_name}
            {m.specialty ? ` — ${SPECIALTY_LABELS[m.specialty]}` : ""}
          </option>
        ))}
      </NativeSelect>
    </span>
  );
}
