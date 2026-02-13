import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  // Base behavior shared by all button variants.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium " +
    "transition-[background-color,color,box-shadow,transform] duration-200 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 " +
    "disabled:pointer-events-none disabled:opacity-50 " +
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/95 hover:shadow-md",
        outline:
          "border border-input bg-background text-foreground shadow-sm hover:bg-muted/40 hover:shadow-md",
        ghost:
          "text-foreground hover:bg-black/[0.04] dark:hover:bg-accent dark:hover:text-accent-foreground",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        // Compatibility aliases kept for a gradual cleanup in callsites.
        secondary:
          "border border-input bg-background text-foreground shadow-sm hover:bg-muted/40 hover:shadow-md",
        link: "text-primary underline-offset-4 hover:underline",
        search:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/95 hover:shadow-md",
      },

      size: {
        default: "ui-control-h px-4",
        sm: "ui-control-h px-3 text-xs",
        // Compatibility alias; prefer `default`.
        lg: "ui-control-h px-4",
        icon: "ui-control-square",
      },

      press: {
        // Compatibility alias; prefer className for one-off motion.
        true: "active:scale-[0.98] disabled:active:scale-100",
        false: "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      press: false,
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, press, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"

    return (
      <Comp
        ref={ref}
        type={!asChild ? (type ?? "button") : type}
        className={cn(buttonVariants({ variant, size, press }), className)}
        {...props}
      />
    )
  }
)

Button.displayName = "Button"

// eslint-disable-next-line react-refresh/only-export-components
export { Button, buttonVariants }
