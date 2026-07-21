import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";

interface ActionCardProps {
  href: string;
  /** Icono grande (nodo lucide), va en un contenedor con fondo suave violeta. */
  icon: React.ReactNode;
  title: string;
  description: React.ReactNode;
  /** Pie de tarjeta opcional (contexto adicional). */
  footer?: React.ReactNode;
}

/**
 * Tarjeta de acción con presencia: icono en contenedor suave violeta, título,
 * descripción, flecha de acción y hover con elevación (shadow + translate). Toda
 * la tarjeta es clicable y accesible por teclado.
 */
export function ActionCard({ href, icon, title, description, footer }: ActionCardProps) {
  return (
    <Link
      href={href}
      className="group block h-full rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <Card className="h-full gap-0 transition-all duration-200 group-hover:-translate-y-0.5 group-hover:shadow-lg group-hover:ring-primary/30">
        <div className="flex items-start gap-3 px-(--card-spacing)">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground ring-1 ring-primary/10 transition-colors group-hover:bg-primary group-hover:text-primary-foreground [&_svg]:h-5 [&_svg]:w-5">
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="flex items-center justify-between gap-2">
              <span>{title}</span>
              <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-all group-hover:translate-x-0.5 group-hover:text-primary" />
            </CardTitle>
            <CardDescription className="mt-1">{description}</CardDescription>
          </div>
        </div>
        {footer && (
          <CardContent className="mt-3 text-sm text-muted-foreground">
            {footer}
          </CardContent>
        )}
      </Card>
    </Link>
  );
}
