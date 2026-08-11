"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { inventarioApi } from "@/lib/api/inventario";
import type {
  InventorySystem,
  SystemKind,
  SystemStatus,
} from "@/lib/types/inventario";

import { KIND_LABEL, STATUS_LABEL } from "./system-card";

const KINDS: SystemKind[] = ["destino", "legado", "externo"];
const STATUSES: SystemStatus[] = [
  "activo",
  "en_construccion",
  "en_migracion",
  "retirado",
];

/**
 * Alta de un sistema en el inventario.
 *
 * El tipo se explica en el propio formulario porque es la decisión con más
 * consecuencias: el sistema `destino` es contra el que reconcilian los agentes de
 * diseño, así que marcar dos por error deja la fase RECONCILE sin poder elegir y
 * los diseños vuelven a salir como si nada existiera.
 */
export function NewSystemDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (system: InventorySystem) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<SystemKind>("legado");
  const [status, setStatus] = useState<SystemStatus>("activo");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const system = await inventarioApi.createSystem({
        name: name.trim(),
        kind,
        status,
        description: description.trim() || null,
      });
      onCreated(system);
      onOpenChange(false);
      setName("");
      setDescription("");
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo crear el sistema.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Nuevo sistema</DialogTitle>
            <DialogDescription>
              Registra un sistema de la organización para poder inventariar su
              esquema, sus módulos y sus APIs.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-1.5">
              <Label htmlFor="sistema-nombre">Nombre</Label>
              <Input
                id="sistema-nombre"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="TMS Moderno"
                required
                autoFocus
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="sistema-tipo">Tipo</Label>
                <NativeSelect
                  id="sistema-tipo"
                  value={kind}
                  onChange={(e) => setKind(e.target.value as SystemKind)}
                >
                  {KINDS.map((k) => (
                    <option key={k} value={k}>
                      {KIND_LABEL[k]}
                    </option>
                  ))}
                </NativeSelect>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="sistema-estado">Estado</Label>
                <NativeSelect
                  id="sistema-estado"
                  value={status}
                  onChange={(e) => setStatus(e.target.value as SystemStatus)}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {STATUS_LABEL[s]}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </div>

            <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
              <strong>Destino</strong> es el sistema al que se migra: es contra
              él que los agentes de diseño reconcilian lo que proponen. Debe
              haber <strong>uno solo</strong>; si hay varios, la reconciliación
              no puede elegir y se salta.
            </p>

            <div className="space-y-1.5">
              <Label htmlFor="sistema-descripcion">Descripción</Label>
              <Textarea
                id="sistema-descripcion"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Qué hace y en qué estado está."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={saving || !name.trim()}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              Registrar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
