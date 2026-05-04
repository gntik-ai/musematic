"""UPD-052 payment_methods sub-bounded-context.

Local mirror of Stripe payment-method records keyed by ``stripe_payment_method_id``.
The model + repository + service layer is consumed by the upgrade endpoint and
by the ``payment_method.attached`` webhook handler.
"""
