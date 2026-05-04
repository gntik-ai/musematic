"""UPD-052 — Stripe customer helpers.

Wraps the synchronous ``stripe.Customer`` SDK calls. The wrapper is thin on
purpose — the main provider class composes it.
"""

from __future__ import annotations

from platform.billing.providers.stripe.client import StripeClient
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


async def create_customer(
    client: StripeClient,
    *,
    workspace_id: UUID,
    tenant_id: UUID,
    email: str,
    metadata_extra: dict[str, str] | None = None,
) -> str:
    """Create a Stripe customer with the workspace+tenant ids in metadata."""
    metadata = {
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        **(metadata_extra or {}),
    }
    customer = await client.call(
        "customer.create",
        lambda: client.stripe.Customer.create(
            email=email,
            metadata=metadata,
        ),
    )
    customer_id = str(customer["id"])
    LOGGER.info(
        "billing.stripe_customer_created",
        customer_id=customer_id,
        tenant_id=str(tenant_id),
        workspace_id=str(workspace_id),
    )
    return customer_id


async def retrieve_customer(client: StripeClient, customer_id: str) -> dict[str, Any]:
    customer = await client.call(
        "customer.retrieve",
        lambda: client.stripe.Customer.retrieve(customer_id),
    )
    return dict(customer)
