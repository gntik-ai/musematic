import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { queryClient } from "@/lib/query-client";
import { resetStreamState } from "@/lib/hooks/use-message-stream";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { resetHomeFixtures } from "@/mocks/handlers/home";
import { resetMarketplaceFixtures } from "@/mocks/handlers";
import {
  resetAdminFixtures,
  resetConversationFixtures,
} from "@/tests/mocks/handlers";
import { setupServer } from "msw/node";
import { handlers } from "@/mocks/handlers";

export const server = setupServer(...handlers);

function defineWritableProperty<T extends object>(
  target: T,
  key: PropertyKey,
  value: unknown,
) {
  Object.defineProperty(target, key, {
    configurable: true,
    writable: true,
    value,
  });
}

beforeAll(() => {
  server.listen({ onUnhandledRequest: "bypass" });
  defineWritableProperty(
    window,
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  defineWritableProperty(window, "scrollTo", vi.fn());
  defineWritableProperty(HTMLElement.prototype, "scrollIntoView", vi.fn());
  defineWritableProperty(
    window,
    "IntersectionObserver",
    vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
      takeRecords: vi.fn(() => []),
    })),
  );

  class ResizeObserverMock {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  }

  defineWritableProperty(window, "ResizeObserver", ResizeObserverMock);
  defineWritableProperty(globalThis, "ResizeObserver", ResizeObserverMock);

  defineWritableProperty(navigator, "clipboard", {
    writeText: vi.fn().mockResolvedValue(undefined),
  });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  queryClient.clear();
  resetHomeFixtures();
  resetMarketplaceFixtures();
  resetAdminFixtures();
  resetConversationFixtures();
  resetStreamState();
  useConversationStore.getState().reset();
  localStorage.clear();
});

afterAll(() => {
  server.close();
});
