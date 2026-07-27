import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        // El contrato visual (altura, foco violeta con glow, placeholder,
        // estado de error) vive en `.field-base` para que inputs, selects y
        // buscadores no se desincronicen nunca.
        "field-base file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground dark:bg-input/30",
        className
      )}
      {...props}
    />
  )
}

export { Input }
