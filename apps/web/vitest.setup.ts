import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { queryClient } from "@/lib/query-client";
import { resetStreamState } from "@/lib/hooks/use-message-stream";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { resetHomeFixtures } from "@/mocks/handlers/home";
import {
  resetAdminFixtures,
  resetConversationFixtures,
} from "@/tests/mocks/handlers";
import { setupServer } from "msw/node";
import { handlers } from "@/mocks/handlers";

export const server = setupServer(...handlers);

beforeAll(() => {
  server.listen({ onUnhandledRequest: "bypass" });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(window, "scrollTo", {
    writable: true,
    value: vi.fn(),
  });
  Object.defineProperty(window, "IntersectionObserver", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
      takeRecords: vi.fn(() => []),
    })),
  });
  Object.defineProperty(navigator, "clipboard", {
    writable: true,
    value: {
      writeText: vi.fn(),
    },
  });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  queryClient.clear();
  resetHomeFixtures();
  resetAdminFixtures();
  resetConversationFixtures();
  resetStreamState();
  useConversationStore.getState().reset();
  localStorage.clear();
});

afterAll(() => {
  server.close();
});
