# Notifications

Notifications owns outbound channels, delivery attempts, webhook verification, dead letters, and alert fanout.

Primary entities include channel configurations, outbound webhooks, delivery rows, and dead-letter entries. The REST surface manages channels and delivery diagnostics. Kafka events and Redis retry state support delivery reliability.

Notifications is used by incidents, accounts, cost governance, and operations health surfaces.
