"""UPD-052 payment_failure_grace sub-bounded-context.

7-day grace state machine triggered by ``invoice.payment_failed`` Stripe
webhooks. Sends day-1/3/5 reminders via UPD-077 notifications and downgrades
the workspace to Free on day 7 if payment is not recovered.
"""
