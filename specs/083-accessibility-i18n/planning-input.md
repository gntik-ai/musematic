# Planning Input — Accessibility (WCAG 2.1 AA) and Internationalization

> Verbatim brownfield input that motivated this spec. Preserved here as a
> planning artifact. The implementation strategy (specific tables,
> services, schemas, code-level integration points, frontend library
> choice) is intentionally deferred to the planning phase. This file is a
> planning input, not a contract.

## Brownfield Context
**Modifies:** Frontend (`apps/ui/`), new bounded context `localization/`
**FRs:** FR-488, FR-489, FR-490, FR-491, FR-492, FR-493

## Summary
Bring the UI to WCAG 2.1 AA accessibility compliance, add internationalization for 6 languages (English, Spanish, French, German, Japanese, Chinese Simplified), dark mode, command palette, keyboard shortcuts, responsive design, and user preferences.

## Frontend Changes

### i18n
- Install `next-intl` or `react-i18next`
- Extract all strings to `messages/{locale}.json`
- Wrap root layout with i18n provider
- Add locale detection from browser and user preference
- Professional translation workflow integration (e.g., Lokalise, Crowdin)

### Accessibility
- Audit all components with axe-core
- Add ARIA labels to all interactive elements
- Ensure keyboard navigation (Tab order, Escape dismisses)
- Color contrast: verify AA ratios, add high-contrast theme
- Text resizability: no fixed font sizes
- Focus indicators on all interactive elements

### Theme
- Add theme provider with light/dark/system options
- Tailwind dark mode via class strategy
- Theme preference persisted per user

### Command Palette
- Install `cmdk` or similar
- Bind to Cmd/Ctrl+K
- Register commands per page (navigate, create, search)
- Help overlay on `?`

### Responsive Design
- Audit breakpoints: mobile (375px), tablet (768px), desktop (1280px+)
- Adapt layouts for read-mostly flows on mobile
- Add PWA manifest and service worker

## Backend Changes

### `localization/` bounded context
```sql
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) UNIQUE,
    default_workspace_id UUID REFERENCES workspaces(id),
    theme VARCHAR(16) DEFAULT 'system', -- light, dark, system, high_contrast
    language VARCHAR(16) DEFAULT 'en',
    timezone VARCHAR(64) DEFAULT 'UTC',
    notification_preferences JSONB DEFAULT '{}',
    data_export_format VARCHAR(32) DEFAULT 'json',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE locale_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    locale_code VARCHAR(16) NOT NULL UNIQUE,
    translations JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1
);
```

## Acceptance Criteria
- [ ] axe-core scan shows zero AA violations
- [ ] All user strings translatable
- [ ] 6 languages delivered at launch
- [ ] Light/dark/system theme works
- [ ] Cmd/Ctrl+K opens command palette
- [ ] Mobile viewport usable for read flows
- [ ] PWA installable
- [ ] User preferences persist
