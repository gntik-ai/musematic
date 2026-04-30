# Musematic - 智能体网格平台

[![Build](https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml)](https://github.com/gntik-ai/musematic/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/gntik-ai/musematic)](./LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28%2B-blue)](https://kubernetes.io/releases/)
[![Version](https://img.shields.io/github/v/release/gntik-ai/musematic)](https://github.com/gntik-ai/musematic/releases)

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

Musematic 是一个开放平台，用于以生产级治理、可观测性、评估和成本控制来运行 AI 智能体集群。它为平台团队提供 Kubernetes 原生控制平面，用于注册智能体、编排多智能体工作、执行策略、衡量质量、追踪决策，并在本地、实验室和托管集群环境之间迁移工作负载。

## 什么是 Musematic？

Musematic 是面向构建自主和半自主 AI 系统团队的工作流引擎和智能体运维平台。它提供围绕智能体的共享控制平面：身份、生命周期、策略执行、运行时编排、上下文工程、记忆、评估、事件响应、日志、指标、链路追踪和预算治理。

该平台面向工程、产品、安全和运营团队，他们需要将 AI 智能体作为可负责的生产工作负载运行，而不是一次性脚本。一个 workspace 可以注册智能体、组合工作流、运行仿真、认证信任属性、观察推理轨迹、比较评估结果，并在工作到达用户或外部系统之前执行成本或安全策略。

Musematic 有意保持可移植性。同一套系统可以运行在本地 kind 集群、小型 k3s 实验室、基于 Hetzner 的生产部署或托管 Kubernetes 环境中。它的架构将 Python 控制平面与 Go 卫星服务分离，使运营者可以扩展对延迟敏感的执行路径，同时保持治理和审计行为集中。

## 核心能力

- **智能体生命周期管理**：按完全限定 namespace 注册、修订、认证、停用和发现智能体。
- **多智能体编排**：协调 workspace 目标、工作流、集群、审批、重试和热路径执行。
- **信任与合规**：通过观察器、裁判、执行器、审计轨迹、隐私控制和证据捕获来执行策略。
- **推理**：通过推理引擎运行 chain-of-thought、tree-of-thought、ReAct、debate、self-correction 和 scaling-inference 模式。
- **评估**：为轨迹评分、运行语义测试、比较实验，并跟踪公平性或漂移指标。
- **可观测性**：检查整个平台的指标、日志、链路追踪、dashboard、告警和审计链事件。
- **成本治理**：按执行归因支出、执行预算、预测用量、检测异常并支持 chargeback。
- **可移植性**：使用标准 Helm 流程部署到 kind、k3s、Hetzner、托管 Kubernetes 或裸金属。

## 快速开始

在热缓存情况下，五分钟完成本地开发安装：

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
open http://localhost:8080
```

`make dev-up` 会创建或复用基于 kind 的本地环境，安装 Helm charts，并写入端到端测试框架使用的测试数据。首次运行可能需要更长时间，因为需要拉取 Docker 镜像和 chart 依赖。

开发时可使用这些辅助命令：

```bash
make dev-logs
make dev-down
make dev-reset
```

有关更深入的设置和运营细节，请参阅[开发指南](./docs/developer-guide/)和[运营指南](./docs/operator-guide/)。

## 安装选项

| 目标 | 使用场景 | 指南 |
|---|---|---|
| kind | 本地开发和类似 CI 的端到端测试 | [kind 安装](./docs/installation/kind.md) |
| k3s | 单节点实验室和小型环境 | [k3s 安装](./docs/installation/k3s.md) |
| 带负载均衡器的 Hetzner | 面向生产的自管理集群 | [Hetzner 安装](./docs/installation/hetzner.md) |
| GKE、EKS 或 AKS | 托管 Kubernetes 部署 | [托管 Kubernetes 安装](./docs/installation/managed-k8s.md) |

所有安装模式都使用仓库自有的同一组 Helm charts，位于 `deploy/helm/`，并使用相同的控制平面契约。

## 架构概览

![架构图](./docs/assets/architecture-overview.svg)

Musematic 使用控制平面和卫星服务架构。Python 控制平面负责 API 编排、有界上下文服务、策略、审计记录和集成。Go 卫星服务负责对延迟敏感的运行时职责：启动智能体 pod、沙箱化代码执行、运行推理模式和管理仿真。

Kafka 在有界上下文之间传递领域事件。PostgreSQL 存储关系状态，Redis 保存热计数器和租约，Qdrant 存储向量嵌入，Neo4j 存储知识图谱关系，ClickHouse 存储分析汇总，OpenSearch 提供全文搜索，S3 兼容对象存储保存较大的工件。

前端是一个 Next.js 应用，消费类型化的 REST、WebSocket 和生成的客户端契约。可观测性是一等能力：Prometheus、Grafana、Jaeger 和 Loki 是部署模型的一部分，dashboard 会随 Helm chart 表面一起入库。

该平台的设计目标是让治理保持集中，同时让执行保持可扩展。运营者可以添加新的有界上下文或卫星能力，而不绕过共同的身份、策略、遥测和审计行为。

## 文档

- [管理指南](./docs/admin-guide/)
- [运营指南](./docs/operator-guide/)
- [开发指南](./docs/developer-guide/)
- [用户指南](./docs/user-guide/)
- [集成](./docs/admin-guide/integrations.md)
- [智能体构建指南](./docs/developer-guide/building-agents.md)
- [系统架构](./docs/system-architecture-v6.md)
- [软件架构](./docs/software-architecture-v6.md)
- [功能需求](./docs/functional-requirements-revised-v6.md)

## 贡献

请参阅 [CONTRIBUTING.md](./CONTRIBUTING.md) 获取贡献指南。该治理文件不属于 UPD-038 范围，可由后续仓库管理任务添加。

## 许可证

请参阅 [LICENSE](./LICENSE) 获取许可证条款。如果某个 checkout 中缺少该文件，则在仓库维护者添加许可证之前，应视为该项目尚未声明开源许可证。

## 社区和支持

- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- 讨论：在 GitHub Discussions 启用之前，请使用 [GitHub Issues](https://github.com/gntik-ai/musematic/issues)。
- Releases: [GitHub Releases](https://github.com/gntik-ai/musematic/releases)
- 安全披露：请参阅 [SECURITY.md](./SECURITY.md) 了解负责任披露指南。
