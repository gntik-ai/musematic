"use client";

import type { TokenPair } from "@/types/auth";
import { useAuthStore } from "@/store/auth-store";

let inflightRefresh: Promise<TokenPair> | null = null;

interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

function getApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

function normalizeTokenPair(payload: RefreshTokenResponse): TokenPair {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    expiresIn: payload.expires_in,
  };
}

export async function refreshAccessToken(): Promise<TokenPair> {
  if (inflightRefresh !== null) {
    return inflightRefresh;
  }

  inflightRefresh = (async () => {
    const { refreshToken, clearAuth, setTokens } = useAuthStore.getState();

    if (!refreshToken) {
      clearAuth();
      throw new Error("Missing refresh token");
    }

    const response = await fetch(`${getApiUrl()}/api/v1/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      clearAuth();
      if (typeof window !== "undefined") {
        window.location.assign("/login");
      }
      throw new Error("Unable to refresh access token");
    }

    const tokenPair = normalizeTokenPair((await response.json()) as RefreshTokenResponse);
    setTokens(tokenPair);
    return tokenPair;
  })();

  try {
    return await inflightRefresh;
  } finally {
    inflightRefresh = null;
  }
}
