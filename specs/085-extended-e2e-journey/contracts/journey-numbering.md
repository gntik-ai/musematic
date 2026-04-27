# Journey Numbering Contract

Feature 085 reconciles the FR-461 journey numbering with the current files under
`tests/e2e/journeys/`.

| Journey | FR-461 / UPD-035 expected persona or flow | Current file state | Feature 085 action |
|---|---|---|---|
| J01 | Administrator bootstrap | `test_j01_admin_bootstrap.py` exists | Extend per FR-520 |
| J02 | Creator to publication | `test_j02_creator_to_publication.py` exists | Extend per FR-520 |
| J03 | Consumer discovery and execution | `test_j03_consumer_discovery_execution.py` exists | Extend per FR-520 |
| J04 | Workspace goal collaboration | `test_j04_workspace_goal_collaboration.py` exists | Extend per FR-520 |
| J05 | Trust governance pipeline | Missing | Add as `test_j05_trust_governance_pipeline.py` |
| J06 | Operator incident response | Missing | Add as `test_j06_operator_incident_response.py` |
| J07 | Evaluator improvement loop | Missing | Add as `test_j07_evaluator_improvement_loop.py` |
| J08 | External A2A / MCP integrator | Missing | Add as `test_j08_external_a2a_mcp.py` |
| J09 | Scientific discovery | Missing | Add as `test_j09_scientific_discovery.py` |
| J10 | Privacy Officer | `test_j10_multi_channel_notifications.py` exists but is not canonical | Rename/rewrite to `test_j10_privacy_officer.py` after feature 072 owner sign-off |
| J11 | Security Officer | Missing | Add as `test_j11_security_officer.py` |
| J12 | Finance Owner | Missing | Add as `test_j12_finance_owner.py` |
| J13 | SRE Multi-Region | Missing | Add as `test_j13_sre_multi_region.py` |
| J14 | Model Steward | Missing | Add as `test_j14_model_steward.py` |
| J15 | Accessibility User | Missing | Add as `test_j15_accessibility_user.py` |
| J16 | Compliance Auditor | Missing | Add as `test_j16_compliance_auditor.py` |
| J17 | Dashboard Consumer | Missing | Add as `test_j17_dashboard_consumer.py` |

Feature 072 owner sign-off for the J10 notifications rename is still pending.
Until that sign-off lands, this contract records the canonical target state and
keeps the existing notifications file untouched.
