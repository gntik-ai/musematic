import { beforeEach, describe, expect, it } from "vitest";
import { useAlertStore } from "@/store/alert-store";

describe("alert-store", () => {
  beforeEach(() => {
    useAlertStore.setState({
      unreadCount: 0,
      isDropdownOpen: false,
    });
  });

  it("starts with no unread alerts and a closed dropdown", () => {
    expect(useAlertStore.getState().unreadCount).toBe(0);
    expect(useAlertStore.getState().isDropdownOpen).toBe(false);
  });

  it("increments unread alerts and resets them when marking all as read", () => {
    const state = useAlertStore.getState();

    state.increment();
    state.increment();

    expect(useAlertStore.getState().unreadCount).toBe(2);

    useAlertStore.getState().markAllAsRead();

    expect(useAlertStore.getState().unreadCount).toBe(0);
  });

  it("clamps unread count to zero and toggles the dropdown state", () => {
    const state = useAlertStore.getState();

    state.setUnreadCount(-4);
    expect(useAlertStore.getState().unreadCount).toBe(0);

    state.setUnreadCount(7);
    state.setDropdownOpen(true);

    expect(useAlertStore.getState().unreadCount).toBe(7);
    expect(useAlertStore.getState().isDropdownOpen).toBe(true);
  });
});
