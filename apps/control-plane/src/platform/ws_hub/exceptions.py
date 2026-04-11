from __future__ import annotations


class WebSocketGatewayError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SubscriptionAuthError(WebSocketGatewayError):
    def __init__(self, code: str, message: str) -> None:
        if code not in {"unauthorized", "resource_not_found"}:
            raise ValueError(f"Unsupported subscription auth error code: {code}")
        super().__init__(code, message)


class ProtocolViolationError(WebSocketGatewayError):
    def __init__(self, code: str, message: str) -> None:
        if code not in {"protocol_violation", "invalid_channel", "invalid_resource_id"}:
            raise ValueError(f"Unsupported protocol violation code: {code}")
        super().__init__(code, message)


class SubscriptionStateError(WebSocketGatewayError):
    def __init__(self, code: str, message: str) -> None:
        if code not in {"already_subscribed", "cannot_unsubscribe_auto"}:
            raise ValueError(f"Unsupported subscription state error code: {code}")
        super().__init__(code, message)

