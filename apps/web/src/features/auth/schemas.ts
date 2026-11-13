import { z } from "zod";

export const MIN_PASSWORD = 12;

const email = z.string().trim().toLowerCase().pipe(z.email("Enter a valid email address."));
const newPassword = z
  .string()
  .min(MIN_PASSWORD, `Use at least ${MIN_PASSWORD} characters. A short phrase works well.`)
  .max(256, "Use 256 characters or fewer.");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password."),
});

export const mfaSchema = z.object({
  code: z
    .string()
    .trim()
    .min(6, "Enter the 6-digit code, or a recovery code.")
    .max(20, "That code is too long."),
});

export const registerSchema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(200),
  email,
  password: newPassword,
  organisation_name: z.string().trim().min(1, "Enter your organisation's name.").max(200),
});

export const inviteRegisterSchema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(200),
  password: newPassword,
});

export const emailSchema = z.object({ email });

export const resetSchema = z
  .object({ password: newPassword, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "The passwords don't match.", path: ["confirm"] });

export const changePasswordSchema = z
  .object({ current_password: z.string().min(1, "Enter your current password."), new_password: newPassword, confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, { message: "The passwords don't match.", path: ["confirm"] });

/** Only allow same-site relative redirects after sign-in (no open redirect). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/overview";
  return next;
}
