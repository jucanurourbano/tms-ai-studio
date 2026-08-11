"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
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
import { ApiError } from "@/lib/api/client";
import { inventarioApi } from "@/lib/api/inventario";
import type {
  DdlImportReport,
  KnowledgeExtractionReport,
} from "@/lib/types/inventario";

/**
 * Carga de un dump DDL o de un documento.
 *
 * Lo que distingue este diálogo: **no se cierra al terminar si hubo hallazgos**.
 * El backend informa de las sentencias que no pudo interpretar (con su línea) y
 * de lo que descartó por no citar evidencia; cerrar el diálogo con un "listo"
 * verde escondería justo el dato que el usuario necesita — que a su esquema le
 * falta una tabla.
 */
export function UploadDialog({
  systemId,
  kind,
  open,
  onOpenChange,
  onUploaded,
}: {
  systemId: string;
  kind: "ddl" | "document";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: () => void;
}) {
  const esDdl = kind === "ddl";
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("core");
  const [subiendo, setSubiendo] = useState(false);
  const [ddlReport, setDdlReport] = useState<DdlImportReport | null>(null);
  const [docReport, setDocReport] = useState<KnowledgeExtractionReport | null>(
    null,
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setSubiendo(true);
    try {
      if (esDdl) {
        const asset = await inventarioApi.uploadDdl(systemId, file, name.trim());
        setDdlReport(asset.import_report);
        toast.success(
          `Esquema cargado (v${asset.version}): ${asset.import_report.tables} tablas`,
        );
        if (asset.import_report.errors.length === 0) {
          onUploaded();
          onOpenChange(false);
        } else {
          onUploaded();
        }
      } else {
        const res = await inventarioApi.uploadDocument(systemId, file);
        setDocReport(res.extraction_report);
        toast.success(
          `Documento leído: ${res.extraction_report.modules} módulos, ${res.extraction_report.entities} entidades`,
        );
        onUploaded();
        if (res.extraction_report.discarded.length === 0) onOpenChange(false);
      }
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo cargar el archivo.",
      );
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {esDdl ? "Subir esquema (DDL)" : "Subir documento"}
            </DialogTitle>
            <DialogDescription>
              {esDdl
                ? "Un archivo .sql con el DDL del esquema. Se lee con un parser, sin IA."
                : "Un .docx, .pdf, .txt o .md que describa el sistema. Se extraen sus módulos, entidades y decisiones."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {esDdl && (
              <div className="space-y-1.5">
                <Label htmlFor="activo-nombre">Nombre del activo</Label>
                <Input
                  id="activo-nombre"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="core"
                />
                <p className="text-xs text-muted-foreground">
                  Volver a subir con el mismo nombre crea una versión nueva; la
                  anterior se conserva.
                </p>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="activo-archivo">Archivo</Label>
              <Input
                id="activo-archivo"
                type="file"
                accept={esDdl ? ".sql" : ".docx,.pdf,.txt,.md"}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>

            {ddlReport && <DdlReportView report={ddlReport} />}
            {docReport && <DocReportView report={docReport} />}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {ddlReport || docReport ? "Cerrar" : "Cancelar"}
            </Button>
            <Button type="submit" disabled={subiendo || !file}>
              {subiendo && <Loader2 className="h-4 w-4 animate-spin" />}
              Cargar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DdlReportView({ report }: { report: DdlImportReport }) {
  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
      <p>
        <strong>{report.tables}</strong> tablas y{" "}
        <strong>{report.columns}</strong> columnas leídas.
        {report.ignored_statements > 0 &&
          ` ${report.ignored_statements} sentencias irrelevantes ignoradas.`}
      </p>
      {report.errors.length > 0 && (
        <div className="space-y-1 rounded border border-red-200 bg-red-50 p-2 text-red-800">
          <p className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" />
            {report.errors.length} sentencias NO se pudieron interpretar
          </p>
          <p>
            Si alguna define una tabla, esa tabla no entró al inventario y los
            agentes propondrán crearla.
          </p>
          <ul className="list-disc space-y-0.5 pl-4">
            {report.errors.slice(0, 5).map((e, i) => (
              <li key={i}>{e.message}</li>
            ))}
          </ul>
        </div>
      )}
      {report.warnings.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-amber-700">
          {report.warnings.slice(0, 5).map((w, i) => (
            <li key={i}>{w.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DocReportView({ report }: { report: KnowledgeExtractionReport }) {
  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
      <p>
        <strong>{report.modules}</strong> módulos,{" "}
        <strong>{report.entities}</strong> entidades,{" "}
        <strong>{report.functionalities}</strong> funcionalidades y{" "}
        <strong>{report.decisions}</strong> decisiones, de {report.fragments}{" "}
        fragmentos.
      </p>
      {report.discarded.length > 0 && (
        <div className="space-y-1 rounded border border-amber-200 bg-amber-50 p-2 text-amber-800">
          <p className="font-semibold">
            {report.discarded.length} elementos descartados
          </p>
          <p>
            Se descarta lo que no cita un fragmento real del documento o llega
            sin evidencia: al inventario no entra nada sin respaldo.
          </p>
          <ul className="list-disc space-y-0.5 pl-4">
            {report.discarded.slice(0, 5).map((d, i) => (
              <li key={i}>
                {d.name} — {d.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
