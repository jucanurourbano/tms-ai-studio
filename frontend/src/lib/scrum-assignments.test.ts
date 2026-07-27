import { describe, expect, it } from "vitest";

import {
  assigneeMap,
  computeSprintLoads,
  fairShare,
  isOverloaded,
  matchesPersonFilter,
  SIN_ASIGNAR,
  sourceMap,
  sprintAssigneeMap,
  unassignedPoints,
} from "@/lib/scrum-assignments";
import type { Specialty } from "@/lib/types/auth";
import type { Story, StoryAssignment, TeamMember } from "@/lib/types/scrum";

function member(id: string, name: string, specialty?: Specialty): TeamMember {
  return {
    id,
    full_name: name,
    institutional_email: `${id}@urbano.com.pe`,
    specialty: specialty ?? null,
    role: "developer",
    is_active: true,
  };
}

const ANA = member("u1", "Ana Pérez", "backend");
const LUIS = member("u2", "Luis Gómez", "frontend");

function story(id: string, points: number | null): Story {
  return { id, story_points: points } as unknown as Story;
}

const STORIES = new Map<string, Story>([
  ["US-001", story("US-001", 5)],
  ["US-002", story("US-002", 3)],
  ["US-003", story("US-003", 8)],
  ["US-004", story("US-004", null)], // sin estimar
]);

function asignacion(storyId: string, user: TeamMember): StoryAssignment {
  return { story_id: storyId, user_id: user.id, source: "story", user };
}

describe("assigneeMap", () => {
  it("indexa por historia y omite las asignaciones sin usuario legible", () => {
    const map = assigneeMap([
      asignacion("US-001", ANA),
      { story_id: "US-002", user_id: "fantasma", source: "story", user: null },
    ]);
    expect(map.get("US-001")?.id).toBe("u1");
    expect(map.has("US-002")).toBe(false);
  });
});

describe("computeSprintLoads", () => {
  it("suma puntos e historias por colaborador, de mayor a menor carga", () => {
    const assignees = assigneeMap([
      asignacion("US-001", ANA), // 5
      asignacion("US-002", LUIS), // 3
      asignacion("US-003", ANA), // 8
    ]);
    const loads = computeSprintLoads(
      ["US-001", "US-002", "US-003"],
      STORIES,
      assignees,
    );
    expect(loads.map((l) => l.member.id)).toEqual(["u1", "u2"]);
    expect(loads[0]).toMatchObject({ stories: 2, points: 13 });
    expect(loads[1]).toMatchObject({ stories: 1, points: 3 });
  });

  it("una historia sin estimar cuenta como historia pero suma 0 puntos", () => {
    const assignees = assigneeMap([asignacion("US-004", ANA)]);
    const loads = computeSprintLoads(["US-004"], STORIES, assignees);
    expect(loads[0]).toMatchObject({ stories: 1, points: 0 });
  });

  it("ignora las historias sin responsable", () => {
    const assignees = assigneeMap([asignacion("US-001", ANA)]);
    const loads = computeSprintLoads(["US-001", "US-002"], STORIES, assignees);
    expect(loads).toHaveLength(1);
  });

  it("sin asignaciones no hay cargas", () => {
    expect(computeSprintLoads(["US-001"], STORIES, new Map())).toEqual([]);
  });
});

describe("unassignedPoints", () => {
  it("suma los puntos de las historias sin responsable", () => {
    const assignees = assigneeMap([asignacion("US-001", ANA)]);
    // US-002 (3) + US-003 (8); US-001 está asignada.
    expect(
      unassignedPoints(["US-001", "US-002", "US-003"], STORIES, assignees),
    ).toBe(11);
  });

  it("es 0 cuando todo está asignado", () => {
    const assignees = assigneeMap([asignacion("US-001", ANA)]);
    expect(unassignedPoints(["US-001"], STORIES, assignees)).toBe(0);
  });
});

describe("umbral de sobrecarga", () => {
  it("el reparto equitativo divide la capacidad entre las personas", () => {
    expect(fairShare(20, 2)).toBe(10);
    expect(fairShare(20, 4)).toBe(5);
  });

  it("sin capacidad o sin personas no hay umbral", () => {
    expect(fairShare(0, 3)).toBe(0);
    expect(fairShare(20, 0)).toBe(0);
  });

  it("marca sobrecarga solo por encima del reparto", () => {
    const share = fairShare(20, 2); // 10
    expect(isOverloaded(13, share)).toBe(true);
    expect(isOverloaded(10, share)).toBe(false); // justo en el reparto, no sobra
    expect(isOverloaded(3, share)).toBe(false);
  });

  it("sin umbral nadie está sobrecargado", () => {
    expect(isOverloaded(99, 0)).toBe(false);
  });
});

describe("matchesPersonFilter", () => {
  const assignees = assigneeMap([asignacion("US-001", ANA)]);

  it("sin filtro pasan todas", () => {
    expect(matchesPersonFilter("US-001", "", assignees)).toBe(true);
    expect(matchesPersonFilter("US-002", "", assignees)).toBe(true);
  });

  it("filtra por colaborador", () => {
    expect(matchesPersonFilter("US-001", "u1", assignees)).toBe(true);
    expect(matchesPersonFilter("US-002", "u1", assignees)).toBe(false);
    expect(matchesPersonFilter("US-001", "u2", assignees)).toBe(false);
  });

  it("«sin asignar» deja solo las historias sin responsable", () => {
    expect(matchesPersonFilter("US-002", SIN_ASIGNAR, assignees)).toBe(true);
    expect(matchesPersonFilter("US-001", SIN_ASIGNAR, assignees)).toBe(false);
  });
});

describe("sourceMap", () => {
  it("distingue la asignación explícita de la heredada del sprint", () => {
    const map = sourceMap([
      { story_id: "US-001", user_id: "u1", source: "story", user: ANA },
      { story_id: "US-002", user_id: "u1", source: "sprint", user: ANA },
    ]);
    expect(map.get("US-001")).toBe("story");
    expect(map.get("US-002")).toBe("sprint");
    expect(map.has("US-003")).toBe(false);
  });
});

describe("sprintAssigneeMap", () => {
  it("indexa el responsable por sprint y omite los ilegibles", () => {
    const map = sprintAssigneeMap([
      { sprint_id: "Sprint 1", user_id: "u1", user: ANA },
      { sprint_id: "Sprint 2", user_id: "fantasma", user: null },
    ]);
    expect(map.get("Sprint 1")?.full_name).toBe("Ana Pérez");
    expect(map.has("Sprint 2")).toBe(false);
  });
});

describe("carga con historias heredadas del sprint", () => {
  it("las heredadas cuentan igual que las explícitas", () => {
    // El backend ya devuelve la cascada resuelta, así que la carga no tiene que
    // saber de dónde viene cada responsable.
    const assignees = assigneeMap([
      { story_id: "US-001", user_id: "u1", source: "story", user: ANA },
      { story_id: "US-002", user_id: "u1", source: "sprint", user: ANA },
    ]);
    const loads = computeSprintLoads(["US-001", "US-002"], STORIES, assignees);
    expect(loads).toHaveLength(1);
    expect(loads[0]).toMatchObject({ stories: 2, points: 8 }); // 5 + 3
  });
});
