import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
export const date = (value?: string | number) =>
  value
    ? new Intl.DateTimeFormat("id-ID", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(typeof value === "number" ? value * 1000 : value))
    : "—";
export const number = (value: number) =>
  new Intl.NumberFormat("id-ID").format(value);
