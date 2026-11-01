from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import DeviceProfile, Ticket
from .base import ProviderNotConfigured, ProviderUnavailable, TicketProvider, TicketUpsert
from .local import LocalTicketProvider


class ZendeskTicketProvider(LocalTicketProvider):
    """Read-only Zendesk adapter with a local MySQL mirror.

    The mirror keeps the Agent deterministic and auditable. Outbound customer replies
    and internal-note writes are intentionally not enabled in this module; they are a
    separate production action with their own approval gate.
    """

    provider_name = "zendesk"

    def __init__(self, db: Session):
        super().__init__(db)
        if not self.is_configured:
            raise ProviderNotConfigured(
                "Zendesk provider requires ZENDESK_SUBDOMAIN, ZENDESK_EMAIL and ZENDESK_API_TOKEN"
            )

    @property
    def is_configured(self) -> bool:
        return bool(settings.zendesk_subdomain and settings.zendesk_email and settings.zendesk_api_token)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=f"https://{settings.zendesk_subdomain}.zendesk.com/api/v2",
            auth=httpx.BasicAuth(f"{settings.zendesk_email}/token", settings.zendesk_api_token),
            timeout=settings.zendesk_timeout_seconds,
        )

    def _request_json(self, path: str, params: dict | None = None) -> dict[str, Any] | None:
        try:
            with self._client() as client:
                response = client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Zendesk request failed: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code in {401, 403}:
            raise ProviderUnavailable("Zendesk authentication or permission failed")
        if response.status_code >= 500:
            raise ProviderUnavailable(f"Zendesk returned {response.status_code}")
        try:
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(f"Zendesk response was invalid: {exc}") from exc

    def _normalize(self, payload: dict[str, Any]) -> TicketUpsert:
        serial_no: str | None = None
        if settings.zendesk_serial_field_id:
            for item in payload.get("custom_fields", []):
                if str(item.get("id")) == str(settings.zendesk_serial_field_id):
                    serial_no = item.get("value")
                    break
        status_map = {
            "new": "open",
            "open": "open",
            "pending": "pending",
            "hold": "pending",
            "solved": "solved",
            "closed": "closed",
        }
        raw_id = str(payload.get("id"))
        return TicketUpsert(
            id=f"ZD-{raw_id}",
            external_id=f"zendesk:{raw_id}",
            subject=payload.get("subject") or "Zendesk support request",
            status=status_map.get(str(payload.get("status", "open")), "open"),
            priority=str(payload.get("priority") or "normal").lower(),
            customer_name=f"Zendesk requester {payload.get('requester_id', 'unknown')}",
            customer_email="",
            serial_no=serial_no,
            channel="Zendesk",
            source="zendesk",
            extra={"zendesk": payload},
        )

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        raw_id = ticket_id.removeprefix("ZD-")
        payload = self._request_json(f"/tickets/{raw_id}.json")
        if not payload or "ticket" not in payload:
            return None
        return self.upsert_ticket(self._normalize(payload["ticket"]))

    def list_tickets(self, status: str | None = None, limit: int = 50) -> list[Ticket]:
        payload = self._request_json("/tickets.json", params={"per_page": min(limit, 100)})
        if not payload:
            return []
        for item in payload.get("tickets", []):
            self.upsert_ticket(self._normalize(item))
        return super().list_tickets(status=status, limit=limit)

    def get_device(self, serial_no: str) -> DeviceProfile | None:
        return super().get_device(serial_no)

