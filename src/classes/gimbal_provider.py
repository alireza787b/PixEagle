# src/classes/gimbal_provider.py

"""
Gimbal provider contract and factory.

The tracker layer consumes normalized gimbal data through this module instead of
constructing a vendor protocol client directly. The current supported provider
is the existing Topotek SIP-over-UDP integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, Union, runtime_checkable

from classes.gimbal_interface import GimbalInterface
from classes.gimbal_types import GimbalData, TrackingState


TOPOTEK_SIP_UDP_PROVIDER = "topotek_sip_udp"
TOPOTEK_PROVIDER_ALIASES = frozenset(
    {
        TOPOTEK_SIP_UDP_PROVIDER,
        "sip_udp",
        "topotek",
        "topotek_sip",
    }
)


class UnknownGimbalProviderError(ValueError):
    """Raised when config requests an unsupported gimbal provider."""


@runtime_checkable
class GimbalInputProvider(Protocol):
    """Normalized input boundary consumed by GimbalTracker."""

    provider_id: str
    display_name: str
    protocol_name: str

    def start_listening(self) -> bool:
        """Start provider IO and make data available to the tracker."""

    def stop_listening(self) -> None:
        """Stop provider IO and release resources."""

    def get_current_data(self) -> Optional[GimbalData]:
        """Return fresh normalized gimbal data, or None when unavailable."""

    def get_connection_status(self) -> str:
        """Return provider connection state for UI/API diagnostics."""

    def get_statistics(self) -> Dict[str, Any]:
        """Return provider-specific counters and state."""

    def get_health_status(self) -> Dict[str, Any]:
        """Return provider health and freshness recommendations."""

    def is_tracking_active(self) -> bool:
        """Return True only when provider reports active target tracking."""

    def get_provider_metadata(self) -> Dict[str, Any]:
        """Return stable metadata for diagnostics and docs."""


@dataclass(frozen=True)
class GimbalProviderConfig:
    """Typed config used to construct a gimbal input provider."""

    provider: str = TOPOTEK_SIP_UDP_PROVIDER
    settings: Optional[Mapping[str, Any]] = None

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "GimbalProviderConfig":
        """Build provider config from the Parameters.GimbalTracker mapping."""
        return cls(
            provider=str(config.get("PROVIDER", TOPOTEK_SIP_UDP_PROVIDER)),
            settings=dict(config),
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Read a provider-specific setting."""
        return (self.settings or {}).get(key, default)


class SipUdpGimbalProvider(GimbalInterface):
    """Topotek SIP-series UDP provider backed by the existing parser/client."""

    provider_id = TOPOTEK_SIP_UDP_PROVIDER
    display_name = "Topotek SIP UDP"
    protocol_name = "topotek_sip_udp"

    def start(self) -> bool:
        """Alias for provider-oriented callers."""
        return self.start_listening()

    def stop(self) -> None:
        """Alias for provider-oriented callers."""
        self.stop_listening()

    def get_provider_metadata(self) -> Dict[str, Any]:
        """Return stable metadata for diagnostics and UI/API surfaces."""
        return {
            "provider": self.provider_id,
            "display_name": self.display_name,
            "protocol": self.protocol_name,
            "transport": "udp",
            "listen_port": self.listen_port,
            "gimbal_ip": self.gimbal_ip,
            "control_port": self.control_port,
            "tracking_states": [state.name for state in TrackingState],
            "coordinate_systems": ["GIMBAL_BODY", "SPATIAL_FIXED"],
            "packet_families": ["GAC", "GIC", "TRC", "OFT"],
        }


def canonicalize_gimbal_provider(provider: str) -> str:
    """Return the canonical provider ID or raise for unsupported providers."""
    provider_key = (provider or TOPOTEK_SIP_UDP_PROVIDER).strip().lower()
    if provider_key in TOPOTEK_PROVIDER_ALIASES:
        return TOPOTEK_SIP_UDP_PROVIDER
    raise UnknownGimbalProviderError(
        f"Unsupported gimbal provider '{provider}'. "
        f"Supported providers: {', '.join(list_supported_gimbal_providers())}"
    )


def list_supported_gimbal_providers() -> List[str]:
    """Return stable provider IDs supported by this build."""
    return [TOPOTEK_SIP_UDP_PROVIDER]


def create_gimbal_provider(
    config: Union[GimbalProviderConfig, Mapping[str, Any]]
) -> GimbalInputProvider:
    """Create a normalized gimbal input provider from typed or mapping config."""
    provider_config = (
        config
        if isinstance(config, GimbalProviderConfig)
        else GimbalProviderConfig.from_mapping(config)
    )
    provider_id = canonicalize_gimbal_provider(provider_config.provider)

    if provider_id == TOPOTEK_SIP_UDP_PROVIDER:
        return SipUdpGimbalProvider(
            listen_port=int(provider_config.get("LISTEN_PORT", 9004)),
            gimbal_ip=str(provider_config.get("UDP_HOST", "192.168.0.108")),
            control_port=int(provider_config.get("UDP_PORT", 9003)),
            connection_timeout=float(provider_config.get("CONNECTION_TIMEOUT", 2.0)),
        )

    raise UnknownGimbalProviderError(
        f"Unsupported gimbal provider '{provider_config.provider}'. "
        f"Supported providers: {', '.join(list_supported_gimbal_providers())}"
    )
