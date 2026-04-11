import type { RoleType } from "@/types/auth";

export interface NavItem {
  id: string;
  label: string;
  icon: string;
  href: string;
  requiredRoles: RoleType[];
  badge?: string | number;
  children?: NavItem[];
}

export interface BreadcrumbSegment {
  label: string;
  href: string | null;
}
