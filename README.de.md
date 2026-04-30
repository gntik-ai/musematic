# Musematic - Agentische Mesh-Plattform

[![Build](https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml)](https://github.com/gntik-ai/musematic/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/gntik-ai/musematic)](./LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28%2B-blue)](https://kubernetes.io/releases/)
[![Version](https://img.shields.io/github/v/release/gntik-ai/musematic)](https://github.com/gntik-ai/musematic/releases)

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

Musematic ist eine offene Plattform zum Betrieb von Flotten aus KI-Agenten mit produktionsreifer Governance, Observability, Evaluation und Kostenkontrolle. Sie gibt Plattformteams eine Kubernetes-native Control Plane zum Registrieren von Agenten, Orchestrieren von Multi-Agenten-Arbeit, Durchsetzen von Richtlinien, Messen von Qualitaet, Nachverfolgen von Entscheidungen und Verschieben von Workloads zwischen lokalen, Labor- und Managed-Cluster-Umgebungen.

## Was ist Musematic?

Musematic ist eine Workflow-Engine und Agent-Operations-Plattform fuer Teams, die autonome und semi-autonome KI-Systeme bauen. Sie stellt die gemeinsame Control Plane rund um Agenten bereit: Identitaet, Lebenszyklus, Richtliniendurchsetzung, Runtime-Orchestrierung, Context Engineering, Speicher, Evaluation, Incident Response, Logs, Metriken, Traces und Budget-Governance.

Die Plattform ist fuer Engineering-, Product-, Security- und Operations-Teams gebaut, die KI-Agenten als nachvollziehbare Produktions-Workloads betreiben muessen statt als einzelne Skripte. Ein Workspace kann Agenten registrieren, Workflows zusammensetzen, Simulationen ausfuehren, Vertrauenseigenschaften zertifizieren, Reasoning-Traces beobachten, Evaluationsergebnisse vergleichen und Kosten- oder Sicherheitsrichtlinien durchsetzen, bevor Arbeit Nutzer oder externe Systeme erreicht.

Musematic ist bewusst portabel. Dasselbe System kann in lokalen kind-Clustern, kleinen k3s-Laboren, Hetzner-gestuetzten Produktionsdeployments oder Managed-Kubernetes-Umgebungen laufen. Die Architektur trennt eine Python-Control-Plane von Go-Satellitendiensten, damit Betreiber latenzkritische Ausfuehrungspfade skalieren koennen, waehrend Governance und Audit-Verhalten zentral bleiben.

## Kernfunktionen

- **Agenten-Lebenszyklusverwaltung**: Agenten ueber vollqualifizierte Namespaces registrieren, ueberarbeiten, zertifizieren, stilllegen und entdecken.
- **Multi-Agenten-Orchestrierung**: Workspace-Ziele, Workflows, Flotten, Freigaben, Wiederholungen und Hot-Path-Ausfuehrung koordinieren.
- **Vertrauen und Compliance**: Richtlinien ueber Observer, Judges, Enforcer, Audit-Trails, Datenschutzkontrollen und Evidenzerfassung durchsetzen.
- **Reasoning**: Chain-of-thought-, Tree-of-thought-, ReAct-, Debate-, Self-correction- und Scaling-inference-Modi ueber die Reasoning Engine ausfuehren.
- **Evaluation**: Trajektorien bewerten, semantische Tests ausfuehren, Experimente vergleichen und Fairness- oder Drift-Indikatoren verfolgen.
- **Observability**: Metriken, Logs, Traces, Dashboards, Alerts und Audit-Chain-Events plattformweit untersuchen.
- **Kosten-Governance**: Ausgaben pro Ausfuehrung zuordnen, Budgets durchsetzen, Nutzung prognostizieren, Anomalien erkennen und Chargeback unterstuetzen.
- **Portabilitaet**: Mit Standard-Helm-Workflows auf kind, k3s, Hetzner, Managed Kubernetes oder Bare Metal deployen.

## Schnellstart

Fuenf Minuten bis zu einer lokalen Entwicklungsinstallation mit warmem Cache:

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
open http://localhost:8080
```

`make dev-up` erstellt oder nutzt die lokale kind-basierte Umgebung, installiert Helm-Charts und seedet die Testdaten, die vom End-to-End-Harness verwendet werden. Erste Laeufe koennen laenger dauern, waehrend Docker-Images und Chart-Abhaengigkeiten geladen werden.

Nutze diese begleitenden Befehle waehrend der Entwicklung:

```bash
make dev-logs
make dev-down
make dev-reset
```

Weitere Details zu Einrichtung und Betrieb findest du im [Entwicklungsleitfaden](./docs/developer-guide/) und im [Betriebsleitfaden](./docs/operator-guide/).

## Installationsoptionen

| Ziel | Anwendungsfall | Leitfaden |
|---|---|---|
| kind | Lokale Entwicklung und CI-aehnliche End-to-End-Tests | [kind-Installation](./docs/installation/kind.md) |
| k3s | Single-Node-Labore und kleine Umgebungen | [k3s-Installation](./docs/installation/k3s.md) |
| Hetzner mit Load Balancer | Produktionsorientierte selbstverwaltete Cluster | [Hetzner-Installation](./docs/installation/hetzner.md) |
| GKE, EKS oder AKS | Managed-Kubernetes-Deployments | [Managed-Kubernetes-Installation](./docs/installation/managed-k8s.md) |

Alle Installationsmodi verwenden dieselben repositoryeigenen Helm-Charts unter `deploy/helm/` und dieselben Control-Plane-Vertraege.

## Architektur auf einen Blick

![Architekturdiagramm](./docs/assets/architecture-overview.svg)

Musematic verwendet eine Architektur aus Control Plane und Satellitendiensten. Die Python-Control-Plane besitzt API-Orchestrierung, Bounded-Context-Services, Richtlinien, Audit-Datensaetze und Integrationen. Die Go-Satellitendienste besitzen latenzkritische Runtime-Verantwortlichkeiten: Starten von Agenten-Pods, Sandboxing von Code-Ausfuehrung, Ausfuehren von Reasoning-Modi und Verwalten von Simulationen.

Kafka transportiert Domain-Events zwischen Bounded Contexts. PostgreSQL speichert relationalen Zustand, Redis haelt Hot Counter und Leases, Qdrant speichert Vektor-Embeddings, Neo4j speichert Knowledge-Graph-Beziehungen, ClickHouse speichert analytische Rollups, OpenSearch bietet Volltextsuche und S3-kompatibler Objektspeicher haelt groessere Artefakte.

Das Frontend ist eine Next.js-Anwendung, die typisierte REST-, WebSocket- und generierte Client-Vertraege konsumiert. Observability ist erstklassig: Prometheus, Grafana, Jaeger und Loki sind Teil des Deployment-Modells, und Dashboards sind in der Helm-Chart-Oberflaeche eingecheckt.

Die Plattform ist so entworfen, dass Governance zentral bleibt, waehrend Ausfuehrung skalierbar bleibt. Betreiber koennen neue Bounded Contexts oder Satellitenfaehigkeiten hinzufuegen, ohne gemeinsame Identitaet, Richtlinien, Telemetrie und Audit-Verhalten zu umgehen.

## Dokumentation

- [Administrationsleitfaden](./docs/admin-guide/)
- [Betriebsleitfaden](./docs/operator-guide/)
- [Entwicklungsleitfaden](./docs/developer-guide/)
- [Benutzerleitfaden](./docs/user-guide/)
- [Integrationen](./docs/admin-guide/integrations.md)
- [Leitfaden zum Erstellen von Agenten](./docs/developer-guide/building-agents.md)
- [Systemarchitektur](./docs/system-architecture-v6.md)
- [Softwarearchitektur](./docs/software-architecture-v6.md)
- [Funktionale Anforderungen](./docs/functional-requirements-revised-v6.md)

## Beitragen

Siehe [CONTRIBUTING.md](./CONTRIBUTING.md) fuer Beitragsrichtlinien. Diese Governance-Datei ist nicht Teil von UPD-038 und kann durch eine nachfolgende Repository-Administrationsaufgabe hinzugefuegt werden.

## Lizenz

Siehe [LICENSE](./LICENSE) fuer Lizenzbedingungen. Wenn die Datei in einem Checkout fehlt, ist das Projekt noch nicht mit einer erklaerten Open-Source-Lizenz versehen, bis Repository-Maintainer eine hinzufuegen.

## Community und Support

- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- Discussions: [GitHub Discussions](https://github.com/gntik-ai/musematic/discussions)
- Releases: [GitHub Releases](https://github.com/gntik-ai/musematic/releases)
- Sicherheitsmeldung: siehe [SECURITY.md](./SECURITY.md) fuer Hinweise zur verantwortungsvollen Offenlegung.
