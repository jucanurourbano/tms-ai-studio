"use client";

import { FileText, Loader2, Sparkles, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { efApi } from "@/lib/api/ef";
import type { AnalyzeResult } from "@/lib/types/ef";
import { cn } from "@/lib/utils";

const MIN_CHARS = 100;
const MAX_MB = 10;
const ALLOWED = [".docx", ".pdf"];

export default function NewAnalysisPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  // Texto libre
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");

  // Documento
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const chars = content.trim().length;
  const textValid = chars >= MIN_CHARS;

  function onAnalyzed(result: AnalyzeResult) {
    if (result.cached) {
      toast.info("Resultado cacheado", {
        description: "Ya existía un análisis para este contenido.",
      });
    } else {
      toast.success("Análisis iniciado");
    }
    router.push(`/agents/ef/jobs/${result.job_id}`);
  }

  function handleError(err: unknown) {
    const message =
      err instanceof ApiError ? err.message : "Error inesperado al analizar.";
    toast.error("No se pudo analizar", { description: message });
  }

  async function analyzeText() {
    setSubmitting(true);
    try {
      const result = await efApi.analyzeText(
        content.trim(),
        title.trim() || undefined,
      );
      onAnalyzed(result);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  function validateFile(f: File): string | null {
    const lower = f.name.toLowerCase();
    if (!ALLOWED.some((ext) => lower.endsWith(ext))) {
      return `Tipo no permitido. Use ${ALLOWED.join(" o ")}.`;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      return `El archivo supera ${MAX_MB} MB.`;
    }
    return null;
  }

  function pickFile(f: File | null) {
    if (!f) return;
    const err = validateFile(f);
    setFileError(err);
    setFile(err ? null : f);
  }

  async function analyzeFile() {
    if (!file) return;
    setSubmitting(true);
    try {
      const result = await efApi.analyzeFile(file);
      onAnalyzed(result);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <PageHeader
        icon="file-search"
        eyebrow="Especificar"
        title="Nuevo análisis"
        description="Analiza un documento de Procesos o pega texto libre."
      />

      <Tabs defaultValue="text">
        <TabsList className="mb-4 w-full sm:w-auto">
          <TabsTrigger value="text" className="gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Texto libre
          </TabsTrigger>
          <TabsTrigger value="file" className="gap-1.5">
            <Upload className="h-3.5 w-3.5" />
            Documento
          </TabsTrigger>
        </TabsList>

        <TabsContent value="text">
          <Card>
            <CardHeader>
              <CardTitle>Texto libre</CardTitle>
              <CardDescription>Mínimo {MIN_CHARS} caracteres.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="title">Título (opcional)</Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Ej. Proceso de siniestros"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="content">Contenido</Label>
                <Textarea
                  id="content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={12}
                  placeholder="Pega aquí el texto del proceso a analizar…"
                  className="resize-y font-mono text-xs leading-relaxed"
                />
                <div className="flex items-center justify-between text-xs">
                  <span
                    className={cn(
                      textValid ? "text-muted-foreground" : "text-amber-600",
                    )}
                  >
                    {chars} caracteres{" "}
                    {textValid ? "✓" : `(faltan ${MIN_CHARS - chars})`}
                  </span>
                </div>
              </div>
              <Button
                onClick={analyzeText}
                disabled={!textValid || submitting}
                className="gap-1.5"
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {submitting ? "Analizando…" : "Analizar"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="file">
          <Card>
            <CardHeader>
              <CardTitle>Documento</CardTitle>
              <CardDescription>
                {ALLOWED.join(" / ")} · máx. {MAX_MB} MB.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {file ? (
                <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-sm">{file.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(0)} KB
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => {
                      setFile(null);
                      setFileError(null);
                    }}
                    aria-label="Quitar archivo"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <div
                  role="button"
                  tabIndex={0}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragging(false);
                    pickFile(e.dataTransfer.files?.[0] ?? null);
                  }}
                  onClick={() => inputRef.current?.click()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      inputRef.current?.click();
                    }
                  }}
                  className={cn(
                    "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-12 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    dragging
                      ? "border-primary bg-accent"
                      : "border-input hover:border-primary/50 hover:bg-muted/40",
                  )}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept=".docx,.pdf"
                    className="hidden"
                    onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                  />
                  <div
                    className={cn(
                      "flex h-11 w-11 items-center justify-center rounded-full transition-colors",
                      dragging
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    <Upload className="h-5 w-5" />
                  </div>
                  <div className="text-sm font-medium">
                    {dragging
                      ? "Suelta el archivo aquí"
                      : "Arrastra un archivo o haz clic para seleccionarlo"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {ALLOWED.join(" / ")} · máx. {MAX_MB} MB
                  </div>
                </div>
              )}
              {fileError && <div className="text-xs text-red-600">{fileError}</div>}
              <Button
                onClick={analyzeFile}
                disabled={!file || submitting}
                className="gap-1.5"
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {submitting ? "Analizando…" : "Analizar"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
