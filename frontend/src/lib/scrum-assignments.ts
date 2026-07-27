// Lógica pura de la capa de asignación del plan Scrum.
//
// Las asignaciones viven FUERA del artefacto (tabla `story_assignments`), así que
// todo lo que se deriva de ellas —carga por persona, sobrecarga, filtros— se
// calcula en el cliente combinando artefacto + asignaciones.

import type {
  SprintAssignment,
  Story,
  StoryAssignment,
  TeamMember,
} from "@/lib/types/scrum";

/** Carga de un colaborador dentro de un sprint. */
export interface MemberLoad {
  member: TeamMember;
  stories: number;
  points: number;
}

/** `story_id` -> responsable resuelto. Ignora asignaciones sin usuario legible. */
export function assigneeMap(
  assignments: StoryAssignment[],
): Map<string, TeamMember> {
  const map = new Map<string, TeamMember>();
  for (const a of assignments) {
    if (a.user) map.set(a.story_id, a.user);
  }
  return map;
}

/**
 * Carga por colaborador en un sprint, de mayor a menor puntos (la sobrecarga
 * salta a la vista primero). Las historias sin estimar cuentan 0 puntos, pero
 * sí cuentan como historia.
 */
export function computeSprintLoads(
  storyIds: string[],
  storyById: Map<string, Story>,
  assignees: Map<string, TeamMember>,
): MemberLoad[] {
  const acc = new Map<string, MemberLoad>();
  for (const sid of storyIds) {
    const member = assignees.get(sid);
    if (!member) continue;
    const points = storyById.get(sid)?.story_points ?? 0;
    const current = acc.get(member.id);
    if (current) {
      current.stories += 1;
      current.points += points;
    } else {
      acc.set(member.id, { member, stories: 1, points });
    }
  }
  return [...acc.values()].sort((x, y) => y.points - x.points);
}

/**
 * `story_id` -> origen del responsable (`story` explícito | `sprint` heredado).
 * Permite distinguir en la UI una asignación decidida a mano de una heredada.
 */
export function sourceMap(
  assignments: StoryAssignment[],
): Map<string, "story" | "sprint"> {
  const map = new Map<string, "story" | "sprint">();
  for (const a of assignments) map.set(a.story_id, a.source);
  return map;
}

/** `sprint_id` -> responsable del sprint completo. */
export function sprintAssigneeMap(
  sprints: SprintAssignment[],
): Map<string, TeamMember> {
  const map = new Map<string, TeamMember>();
  for (const s of sprints) {
    if (s.user) map.set(s.sprint_id, s.user);
  }
  return map;
}

/** Puntos del sprint que siguen sin responsable. */
export function unassignedPoints(
  storyIds: string[],
  storyById: Map<string, Story>,
  assignees: Map<string, TeamMember>,
): number {
  return storyIds
    .filter((sid) => !assignees.has(sid))
    .reduce((sum, sid) => sum + (storyById.get(sid)?.story_points ?? 0), 0);
}

/**
 * Umbral de sobrecarga: el **reparto equitativo** de la capacidad del sprint
 * entre las personas que tienen historias en él.
 *
 * Es la señal más barata y explicable con los datos que hay: no existe capacidad
 * individual declarada por colaborador, así que se compara contra lo que le
 * tocaría a cada uno si el sprint se repartiera por igual. Devuelve 0 (sin
 * umbral) cuando no hay capacidad o no hay nadie asignado.
 */
export function fairShare(capacityPoints: number, people: number): number {
  if (people <= 0 || capacityPoints <= 0) return 0;
  return capacityPoints / people;
}

/** ¿Esta carga supera el reparto equitativo? */
export function isOverloaded(points: number, share: number): boolean {
  return share > 0 && points > share;
}

/** Valor especial del filtro por responsable para "historias sin asignar". */
export const SIN_ASIGNAR = "__sin__";

/**
 * ¿La historia pasa el filtro "ver historias de"?
 * `""` = todas; `SIN_ASIGNAR` = solo las que no tienen responsable.
 */
export function matchesPersonFilter(
  storyId: string,
  filter: string,
  assignees: Map<string, TeamMember>,
): boolean {
  if (filter === "") return true;
  if (filter === SIN_ASIGNAR) return !assignees.has(storyId);
  return assignees.get(storyId)?.id === filter;
}
