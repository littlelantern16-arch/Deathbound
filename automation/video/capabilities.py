"""Provider capability model and ₹0 production-cost policy.

Extends the existing provider-neutral adapter (commit 48e75b0) with an
explicit capability report and a hard production-cost gate.

Policy (non-negotiable business constraint):

    production_cost_policy = "ZERO_RUPEE_ONLY"

Under this policy a provider with ``requires_payment == true`` is refused
for production execution. There is no silent paid fallback anywhere in the
pipeline: the gate raises and the run stops. Free services are acceptable
only when they are genuinely usable without payment.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Canonical capability keys (superset; providers declare what they support).
CAPABILITY_KEYS = [
    "text_to_video",
    "image_to_video",
    "reference_images",
    "first_frame_conditioning",
    "last_frame_conditioning",
    "video_extension",
    "seed_control",
    "negative_prompt",
    "width_height_control",
    "fps_control",
    "duration_control",
    "local_execution",
    "remote_execution",
    "requires_credentials",
    "requires_payment",
]

PRODUCTION_COST_POLICY = "ZERO_RUPEE_ONLY"


class PolicyViolation(RuntimeError):
    """Raised when a provider violates the ₹0 production-cost policy."""


class ProviderPolicy:
    """Hard production-cost gate. No silent paid fallback."""

    def __init__(self, policy: str = PRODUCTION_COST_POLICY) -> None:
        if policy != PRODUCTION_COST_POLICY:
            raise PolicyViolation(
                f"Unsupported production cost policy: {policy!r}. "
                f"Deathbound operates under {PRODUCTION_COST_POLICY} only."
            )
        self.policy = policy

    def evaluate(self, capabilities: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a capability report against the policy.

        Returns a report dict; raises :class:`PolicyViolation` for payment
        or missing/ambiguous cost declarations.
        """
        requires_payment = capabilities.get("requires_payment")
        if requires_payment is None:
            raise PolicyViolation(
                "Provider does not declare 'requires_payment'; refusing to "
                "guess cost status under ZERO_RUPEE_ONLY."
            )
        if requires_payment is True:
            raise PolicyViolation(
                "Provider requires payment; blocked under "
                f"{self.policy}. No silent paid fallback is permitted."
            )
        return {
            "policy": self.policy,
            "allowed": True,
            "requires_payment": requires_payment,
            "requires_credentials": bool(capabilities.get("requires_credentials")),
        }

    def ensure_allowed(self, provider: Any) -> Dict[str, Any]:
        """Gate a provider instance; raise on policy violation."""
        return self.evaluate(getattr(provider, "capabilities", {}))


def validate_capabilities(capabilities: Dict[str, Any]) -> List[str]:
    """Structural validation of a capability report. Returns error list."""
    errors: List[str] = []
    if not isinstance(capabilities, dict):
        return ["capabilities must be a dict"]
    for key in ("text_to_video", "image_to_video"):
        if key not in capabilities:
            errors.append(f"missing required capability: {key}")
    if "requires_payment" not in capabilities:
        errors.append("missing required capability: requires_payment")
    if "requires_credentials" not in capabilities:
        errors.append("missing required capability: requires_credentials")
    execution = capabilities.get("local_execution"), capabilities.get(
        "remote_execution"
    )
    if not any(execution):
        errors.append("provider must declare local_execution or remote_execution")
    return errors


def capability_report(provider: Any) -> Dict[str, Any]:
    """Full capability + policy report for one provider instance."""
    capabilities = dict(getattr(provider, "capabilities", {}))
    structural_errors = validate_capabilities(capabilities)
    report: Dict[str, Any] = {
        "provider_id": getattr(provider, "provider_id", "unknown"),
        "capabilities": capabilities,
        "capability_errors": structural_errors,
    }
    if structural_errors:
        report["policy_compatible"] = False
        report["policy_error"] = "capability declaration invalid"
        return report
    try:
        policy_result = ProviderPolicy().evaluate(capabilities)
        report["policy_compatible"] = True
        report["policy"] = policy_result
    except PolicyViolation as exc:
        report["policy_compatible"] = False
        report["policy_error"] = str(exc)
    return report
