# Musematic - Plataforma de malla agentica

[![Build](https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml)](https://github.com/gntik-ai/musematic/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/gntik-ai/musematic)](./LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28%2B-blue)](https://kubernetes.io/releases/)
[![Version](https://img.shields.io/github/v/release/gntik-ai/musematic)](https://github.com/gntik-ai/musematic/releases)

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

Musematic es una plataforma abierta para operar flotas de agentes de IA con gobernanza, observabilidad, evaluacion y control de costes de nivel productivo. Ofrece a los equipos de plataforma un plano de control nativo de Kubernetes para registrar agentes, orquestar trabajo multiagente, aplicar politicas, medir calidad, trazar decisiones y mover cargas entre entornos locales, de laboratorio y de clusters gestionados.

## ¿Que es Musematic?

Musematic es un motor de flujos de trabajo y una plataforma de operaciones de agentes para equipos que crean sistemas de IA autonomos y semiautonomos. Proporciona el plano de control compartido alrededor de los agentes: identidad, ciclo de vida, aplicacion de politicas, orquestacion de ejecucion, ingenieria de contexto, memoria, evaluacion, respuesta a incidentes, logs, metricas, trazas y gobernanza de presupuestos.

La plataforma esta pensada para equipos de ingenieria, producto, seguridad y operaciones que necesitan ejecutar agentes de IA como cargas productivas responsables, no como scripts aislados. Un workspace puede registrar agentes, componer flujos de trabajo, ejecutar simulaciones, certificar propiedades de confianza, observar trazas de razonamiento, comparar resultados de evaluacion y aplicar politicas de coste o seguridad antes de que el trabajo llegue a usuarios o sistemas externos.

Musematic es deliberadamente portable. El mismo sistema puede ejecutarse en clusters kind locales, laboratorios k3s pequenos, despliegues productivos sobre Hetzner o entornos Kubernetes gestionados. Su arquitectura separa un plano de control en Python de servicios satelite en Go para que los operadores puedan escalar rutas de ejecucion sensibles a latencia mientras mantienen centralizadas la gobernanza y la auditoria.

## Capacidades principales

- **Gestion del ciclo de vida de agentes**: registrar, revisar, certificar, retirar y descubrir agentes por namespace plenamente cualificado.
- **Orquestacion multiagente**: coordinar objetivos de workspace, flujos de trabajo, flotas, aprobaciones, reintentos y ejecucion en rutas calientes.
- **Confianza y cumplimiento**: aplicar politicas mediante observadores, jueces, ejecutores, pistas de auditoria, controles de privacidad y captura de evidencias.
- **Razonamiento**: ejecutar modos chain-of-thought, tree-of-thought, ReAct, debate, autocorreccion y scaling-inference mediante el motor de razonamiento.
- **Evaluacion**: puntuar trayectorias, ejecutar pruebas semanticas, comparar experimentos y seguir indicadores de equidad o deriva.
- **Observabilidad**: inspeccionar metricas, logs, trazas, dashboards, alertas y eventos de cadena de auditoria en toda la plataforma.
- **Gobernanza de costes**: atribuir gasto por ejecucion, aplicar presupuestos, prever uso, detectar anomalias y soportar chargeback.
- **Portabilidad**: desplegar en kind, k3s, Hetzner, Kubernetes gestionado o bare metal con flujos Helm estandar.

## Inicio rapido

Cinco minutos para una instalacion local de desarrollo con cache caliente:

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
open http://localhost:8080
```

`make dev-up` crea o reutiliza el entorno local basado en kind, instala los charts de Helm y carga los datos de prueba usados por el arnes end-to-end. Las primeras ejecuciones pueden tardar mas mientras se descargan imagenes Docker y dependencias de charts.

Usa estos comandos complementarios durante el desarrollo:

```bash
make dev-logs
make dev-down
make dev-reset
```

Consulta la [guia de desarrollo](./docs/developer-guide/) y la [guia de operaciones](./docs/operator-guide/) para una configuracion y operacion mas detalladas.

## Opciones de instalacion

| Destino | Caso de uso | Guia |
|---|---|---|
| kind | Desarrollo local y pruebas end-to-end similares a CI | [Instalacion en kind](./docs/installation/kind.md) |
| k3s | Laboratorios de un solo nodo y entornos pequenos | [Instalacion en k3s](./docs/installation/k3s.md) |
| Hetzner con balanceador de carga | Clusters autogestionados orientados a produccion | [Instalacion en Hetzner](./docs/installation/hetzner.md) |
| GKE, EKS o AKS | Despliegues Kubernetes gestionados | [Instalacion en Kubernetes gestionado](./docs/installation/managed-k8s.md) |

Todos los modos de instalacion usan los mismos charts de Helm propiedad del repositorio en `deploy/helm/` y los mismos contratos del plano de control.

## Arquitectura de un vistazo

![Diagrama de arquitectura](./docs/assets/architecture-overview.svg)

Musematic usa una arquitectura de plano de control y servicios satelite. El plano de control en Python posee la orquestacion de API, los servicios de contextos acotados, las politicas, los registros de auditoria y las integraciones. Los servicios satelite en Go poseen responsabilidades de runtime sensibles a latencia: lanzar pods de agentes, aislar ejecucion de codigo, ejecutar modos de razonamiento y gestionar simulaciones.

Kafka transporta eventos de dominio entre contextos acotados. PostgreSQL almacena estado relacional, Redis mantiene contadores calientes y leases, Qdrant almacena embeddings vectoriales, Neo4j almacena relaciones de grafos de conocimiento, ClickHouse almacena rollups analiticos, OpenSearch proporciona busqueda de texto completo y el almacenamiento compatible con S3 conserva artefactos grandes.

El frontend es una aplicacion Next.js que consume contratos tipados REST, WebSocket y clientes generados. La observabilidad es de primera clase: Prometheus, Grafana, Jaeger y Loki forman parte del modelo de despliegue, y los dashboards se versionan dentro de la superficie de charts de Helm.

La plataforma esta disenada para que la gobernanza siga centralizada mientras la ejecucion sigue siendo escalable. Los operadores pueden anadir nuevos contextos acotados o capacidades satelite sin eludir identidad, politicas, telemetria ni auditoria comunes.

## Documentacion

- [Guia de administracion](./docs/admin-guide/)
- [Guia de operaciones](./docs/operator-guide/)
- [Guia de desarrollo](./docs/developer-guide/)
- [Guia de usuario](./docs/user-guide/)
- [Integraciones](./docs/admin-guide/integrations.md)
- [Guia para crear agentes](./docs/developer-guide/building-agents.md)
- [Arquitectura del sistema](./docs/system-architecture-v6.md)
- [Arquitectura de software](./docs/software-architecture-v6.md)
- [Requisitos funcionales](./docs/functional-requirements-revised-v6.md)

## Contribuir

Consulta [CONTRIBUTING.md](./CONTRIBUTING.md) para las pautas de contribucion. Ese archivo de gobernanza no forma parte de UPD-038 y puede ser agregado por una tarea posterior de administracion del repositorio.

## Licencia

Consulta [LICENSE](./LICENSE) para los terminos de licencia. Si el archivo no existe en un checkout, considera que el proyecto aun no tiene una licencia open source declarada hasta que los mantenedores del repositorio anadan una.

## Comunidad y soporte

- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- Discussions: [GitHub Discussions](https://github.com/gntik-ai/musematic/discussions)
- Releases: [GitHub Releases](https://github.com/gntik-ai/musematic/releases)
- Divulgacion de seguridad: consulta [SECURITY.md](./SECURITY.md) para la guia de divulgacion responsable.
