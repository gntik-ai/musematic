import { z } from "zod";

export const previewSourceSchema = z.object({
  origin: z.string(),
  snippet: z.string(),
  score: z.number(),
  included: z.boolean(),
  classification: z.string(),
  reason: z.string().nullable().optional(),
});

export const profilePreviewResponseSchema = z.object({
  sources: z.array(previewSourceSchema),
  mock_response: z.string(),
  completion_metadata: z.record(z.unknown()),
  was_fallback: z.boolean(),
});

export const contractPreviewResponseSchema = z.object({
  clauses_triggered: z.array(z.string()),
  clauses_satisfied: z.array(z.string()),
  clauses_violated: z.array(z.string()),
  final_action: z.enum(["continue", "warn", "throttle", "escalate", "terminate"]),
  mock_response: z.string().nullable().optional(),
  was_fallback: z.boolean(),
});

export const contractTemplateSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  category: z.string(),
  template_content: z.record(z.unknown()),
  version_number: z.number(),
  forked_from_template_id: z.string().nullable(),
  created_by_user_id: z.string().nullable(),
  is_platform_authored: z.boolean(),
  is_published: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});

