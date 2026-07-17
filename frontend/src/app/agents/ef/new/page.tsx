"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

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
    <div className="p-6 max-w-3xl">
      <header className="mb-5">
        <h1 className="text-xl font-heading font-semibold">Nuevo análisis</h1>
        <p className="text-sm text-muted-foreground">
          Analiza un documento de Procesos o pega texto libre.
        </p>
      </header>

      <Tabs defaultValue="text">
        <TabsList>
          <TabsTrigger value="text">Texto libre</TabsTrigger>
          <TabsTrigger value="file">Documento</TabsTrigger>
        </TabsList>

        <TabsContent value="text">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Texto libre</CardTitle>
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
                  className="font-mono text-xs"
                />
                <div
                  className={
                    "text-xs " +
                    (textValid ? "text-muted-foreground" : "text-amber-600")
                  }
                >
                  {chars} caracteres{" "}
                  {textValid ? "" : `(faltan ${MIN_CHARS - chars})`}
                </div>
              </div>
              <Button onClick={analyzeText} disabled={!textValid || submitting}>
                {submitting ? "Analizando…" : "Analizar"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="file">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Documento</CardTitle>
              <CardDescription>
                {ALLOWED.join(" / ")} · máx. {MAX_MB} MB.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
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
                className={
                  "flex flex-col items-center justify-center rounded-md border-2 border-dashed px-4 py-10 text-center cursor-pointer transition-colors " +
                  (dragging ? "border-primary bg-accent" : "border-input")
                }
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".docx,.pdf"
                  className="hidden"
                  onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                />
                {file ? (
                  <div className="text-sm">
                    <span className="font-mono">{file.name}</span>
                    <div className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(0)} KB
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    Arrastra un archivo o haz clic para seleccionarlo
                  </div>
                )}
              </div>
              {fileError && <div className="text-xs text-red-600">{fileError}</div>}
              <Button onClick={analyzeFile} disabled={!file || submitting}>
                {submitting ? "Analizando…" : "Analizar"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
