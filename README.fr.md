# Musematic - Plateforme de maillage agentique

[![Build](https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml)](https://github.com/gntik-ai/musematic/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/gntik-ai/musematic)](./LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28%2B-blue)](https://kubernetes.io/releases/)
[![Version](https://img.shields.io/github/v/release/gntik-ai/musematic)](https://github.com/gntik-ai/musematic/releases)

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

Musematic est une plateforme ouverte pour exploiter des flottes d'agents IA avec une gouvernance, une observabilite, une evaluation et un controle des couts de niveau production. Elle fournit aux equipes plateforme un plan de controle natif Kubernetes pour enregistrer des agents, orchestrer du travail multi-agent, appliquer des politiques, mesurer la qualite, tracer les decisions et deplacer les workloads entre environnements locaux, de laboratoire et clusters geres.

## Qu'est-ce que Musematic ?

Musematic est un moteur de workflows et une plateforme d'operations d'agents pour les equipes qui construisent des systemes IA autonomes et semi-autonomes. Elle fournit le plan de controle partage autour des agents : identite, cycle de vie, application des politiques, orchestration runtime, ingenierie du contexte, memoire, evaluation, reponse aux incidents, logs, metriques, traces et gouvernance budgetaire.

La plateforme est concue pour les equipes d'ingenierie, produit, securite et operations qui doivent executer des agents IA comme des workloads de production responsables plutot que comme des scripts ponctuels. Un workspace peut enregistrer des agents, composer des workflows, lancer des simulations, certifier des proprietes de confiance, observer des traces de raisonnement, comparer des resultats d'evaluation et appliquer des politiques de cout ou de securite avant que le travail n'atteigne des utilisateurs ou des systemes externes.

Musematic est volontairement portable. Le meme systeme peut fonctionner dans des clusters kind locaux, de petits laboratoires k3s, des deploiements production sur Hetzner ou des environnements Kubernetes geres. Son architecture separe un plan de controle Python de services satellites Go afin que les operateurs puissent mettre a l'echelle les chemins d'execution sensibles a la latence tout en gardant la gouvernance et l'audit centralises.

## Capacites principales

- **Gestion du cycle de vie des agents** : enregistrer, reviser, certifier, decommissionner et decouvrir des agents par namespace pleinement qualifie.
- **Orchestration multi-agent** : coordonner les objectifs de workspace, workflows, flottes, approbations, reprises et executions hot-path.
- **Confiance et conformite** : appliquer des politiques via observateurs, juges, enforcers, pistes d'audit, controles de confidentialite et capture de preuves.
- **Raisonnement** : executer les modes chain-of-thought, tree-of-thought, ReAct, debate, self-correction et scaling-inference via le moteur de raisonnement.
- **Evaluation** : noter les trajectoires, lancer des tests semantiques, comparer les experiences et suivre les indicateurs d'equite ou de derive.
- **Observabilite** : inspecter les metriques, logs, traces, dashboards, alertes et evenements de chaine d'audit dans toute la plateforme.
- **Gouvernance des couts** : attribuer les depenses par execution, appliquer les budgets, prevoir l'usage, detecter les anomalies et prendre en charge le chargeback.
- **Portabilite** : deployer sur kind, k3s, Hetzner, Kubernetes gere ou bare metal avec des workflows Helm standard.

## Demarrage rapide

Cinq minutes pour une installation locale de developpement avec cache chaud :

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
open http://localhost:8080
```

`make dev-up` cree ou reutilise l'environnement local base sur kind, installe les charts Helm et initialise les donnees de test utilisees par le harnais end-to-end. Les premieres executions peuvent prendre plus de temps pendant le telechargement des images Docker et des dependances de charts.

Utilisez ces commandes compagnons pendant le developpement :

```bash
make dev-logs
make dev-down
make dev-reset
```

Consultez le [guide de developpement](./docs/development/) et le [guide d'exploitation](./docs/operations/) pour des details plus approfondis sur la configuration et l'exploitation.

## Options d'installation

| Cible | Cas d'utilisation | Guide |
|---|---|---|
| kind | Developpement local et tests end-to-end proches de la CI | [Harnais E2E](./tests/e2e/README.md) |
| k3s | Laboratoires mono-noeud et petits environnements | [Guide d'exploitation](./docs/operations/) |
| Hetzner avec repartiteur de charge | Clusters autogeres orientes production | [Guide d'exploitation](./docs/operations/) |
| GKE, EKS ou AKS | Deploiements Kubernetes geres | [Guide d'exploitation](./docs/operations/) |

Tous les modes d'installation utilisent les memes charts Helm detenus par le depot sous `deploy/helm/` et les memes contrats du plan de controle.

## Apercu de l'architecture

![Schema d'architecture](./docs/assets/architecture-overview.svg)

Musematic utilise une architecture de plan de controle et de services satellites. Le plan de controle Python possede l'orchestration API, les services de bounded context, les politiques, les enregistrements d'audit et les integrations. Les services satellites Go possedent les responsabilites runtime sensibles a la latence : lancer les pods d'agents, isoler l'execution de code, executer les modes de raisonnement et gerer les simulations.

Kafka transporte les evenements de domaine entre bounded contexts. PostgreSQL stocke l'etat relationnel, Redis conserve les compteurs chauds et les leases, Qdrant stocke les embeddings vectoriels, Neo4j stocke les relations de graphe de connaissances, ClickHouse stocke les rollups analytiques, OpenSearch fournit la recherche plein texte et le stockage compatible S3 conserve les artefacts volumineux.

Le frontend est une application Next.js qui consomme des contrats REST, WebSocket et clients generes types. L'observabilite est de premier ordre : Prometheus, Grafana, Jaeger et Loki font partie du modele de deploiement, et les dashboards sont versionnes dans la surface des charts Helm.

La plateforme est concue pour que la gouvernance reste centralisee tandis que l'execution reste scalable. Les operateurs peuvent ajouter de nouveaux bounded contexts ou des capacites satellites sans contourner l'identite, les politiques, la telemetrie et l'audit communs.

## Documentation

- [Guide d'administration](./docs/administration/)
- [Guide d'exploitation](./docs/operations/)
- [Guide de developpement](./docs/development/)
- [Documentation des fonctionnalites](./docs/features/)
- [Integrations](./docs/integrations/)
- [Guide des agents](./docs/agents.md)
- [Architecture systeme](./docs/system-architecture-v5.md)
- [Architecture logicielle](./docs/software-architecture-v5.md)
- [Exigences fonctionnelles](./docs/functional-requirements-revised-v6.md)

## Contribuer

Consultez [CONTRIBUTING.md](./CONTRIBUTING.md) pour les consignes de contribution. Ce fichier de gouvernance ne fait pas partie d'UPD-038 et pourra etre ajoute par une tache ulterieure d'administration du depot.

## Licence

Consultez [LICENSE](./LICENSE) pour les conditions de licence. Si le fichier est absent dans un checkout, considerez que le projet ne porte pas encore de licence open source declaree jusqu'a ce que les mainteneurs du depot en ajoutent une.

## Communaute et support

- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- Discussions: [GitHub Discussions](https://github.com/gntik-ai/musematic/discussions)
- Releases: [GitHub Releases](https://github.com/gntik-ai/musematic/releases)
- Divulgation de securite : consultez [SECURITY.md](./SECURITY.md). Ce fichier est un futur artefact d'administration du depot hors UPD-038.
