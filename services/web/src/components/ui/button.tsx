import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-[background-color,color,transform,box-shadow] duration-150 hover:scale-[1.05] active:scale-[0.95] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 disabled:hover:scale-100 disabled:active:scale-100 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary hover:shadow-md",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-input bg-background text-foreground shadow-sm hover:bg-background hover:text-foreground hover:shadow-md active:bg-background active:text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "ui-control-h px-4",
        sm: "ui-control-h px-3 text-xs",
        lg: "ui-control-h px-8",
        icon: "ui-control-square",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  searchBehavior?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, searchBehavior = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    const resolvedVariant = variant ?? "default"

    return (
      <Comp
        className={cn(
          buttonVariants({ variant, size }),
          searchBehavior && resolvedVariant === "default"
            ? "hover:text-background hover:bg-primary/95 transition-transform duration-200 hover:scale-[1.05] active:scale-50 disabled:hover:scale-100"
            : null,
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
