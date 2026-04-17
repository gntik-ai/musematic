"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/types/api";
import { useAuthStore } from "@/store/auth-store";
import type { AgentUploadResult } from "@/lib/types/agent-management";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ValidationErrorPayload {
  validation_errors?: string[];
  message?: string;
}

export class UploadValidationError extends ApiError {
  public readonly validationErrors: string[];

  constructor(message: string, validationErrors: string[]) {
    super("validation_error", message, 422, undefined, {
      validation_errors: validationErrors,
    });
    this.name = "UploadValidationError";
    this.validationErrors = validationErrors;
  }
}

export interface UploadAgentPackageVariables {
  workspaceId: string;
  file: File;
}

function parsePayload<T>(rawPayload: string): T | null {
  if (rawPayload.length === 0) {
    return null;
  }

  try {
    return JSON.parse(rawPayload) as T;
  } catch {
    return null;
  }
}

export function useUploadAgentPackage() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const queryClient = useQueryClient();
  const requestRef = useRef<XMLHttpRequest | null>(null);
  const [progress, setProgress] = useState(0);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const mutation = useMutation({
    mutationFn: ({ file, workspaceId }: UploadAgentPackageVariables) =>
      new Promise<AgentUploadResult>((resolve, reject) => {
        const formData = new FormData();
        formData.append("package", file);
        formData.append("workspace_id", workspaceId);

        const request = new XMLHttpRequest();
        requestRef.current = request;
        setProgress(0);
        setValidationErrors([]);

        request.upload.onprogress = (event) => {
          if (!event.lengthComputable || event.total === 0) {
            return;
          }

          setProgress(Math.round((event.loaded / event.total) * 100));
        };

        request.onreadystatechange = () => {
          if (request.readyState !== XMLHttpRequest.DONE) {
            return;
          }

          requestRef.current = null;
          const payload = parsePayload<AgentUploadResult | ValidationErrorPayload>(
            request.responseText,
          );

          if (request.status >= 200 && request.status < 300) {
            setProgress(100);
            resolve((payload ?? {
              agent_fqn: "",
              status: "draft",
              validation_errors: [],
            }) as AgentUploadResult);
            return;
          }

          if (request.status === 422) {
            const errors =
              "validation_errors" in (payload ?? {})
                ? (((payload as ValidationErrorPayload | null)?.validation_errors ?? []) as string[])
                : [];
            setValidationErrors(errors);
            reject(
              new UploadValidationError(
                (payload as ValidationErrorPayload | null)?.message ??
                  "Upload validation failed.",
                errors,
              ),
            );
            return;
          }

          reject(
            new ApiError(
              "upload_failed",
              request.statusText || "Agent upload failed.",
              request.status,
            ),
          );
        };

        request.onerror = () => {
          requestRef.current = null;
          reject(new ApiError("network_error", "Unable to upload the agent package.", 0));
        };

        request.onabort = () => {
          requestRef.current = null;
          reject(new ApiError("upload_aborted", "Upload cancelled.", 0));
        };

        request.open("POST", `${API_BASE_URL}/api/v1/registry/agents/upload`);
        if (accessToken) {
          request.setRequestHeader("Authorization", `Bearer ${accessToken}`);
        }
        request.send(formData);
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-management", "catalog"] });
    },
  });

  return {
    ...mutation,
    progress,
    validationErrors,
    abort: () => {
      requestRef.current?.abort();
      requestRef.current = null;
      setProgress(0);
    },
  };
}
