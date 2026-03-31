"""In-memory Codex task bridge for API-free interactive pipeline steps."""

from __future__ import annotations

import base64
import json
from typing import Any, Callable, Dict, Optional


Validator = Callable[[Any], Any]


def _json_dumps(payload: Any) -> str:
    """Serialize a payload with stable UTF-8 JSON settings."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def encode_state_token(responses: Dict[str, Any]) -> str:
    """Encode resolved step responses into a compact resumable token."""
    payload = _json_dumps(responses).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_state_token(token: Optional[str]) -> Dict[str, Any]:
    """Decode a resumable state token into a step-response mapping."""
    if not token:
        return {}

    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid Codex state token: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Invalid Codex state token: payload must be an object.")
    return payload


class CodexTaskPending(RuntimeError):
    """Raised when a Codex-managed step has a request but no response yet."""

    def __init__(self, step: str, request_payload: Dict[str, Any], state_token: str):
        self.step = step
        self.request_payload = request_payload
        self.state_token = state_token
        super().__init__(
            "Codex task pending for step "
            f"'{step}'. Resume with the provided state token and a JSON response."
        )

    @property
    def request_json(self) -> str:
        """Return the pending request as pretty JSON for display."""
        return json.dumps(self.request_payload, ensure_ascii=False, indent=2)


class CodexTaskRunner:
    """Resolve structured Codex tasks from in-memory responses only."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        self.responses: Dict[str, Any] = dict(responses or {})

    def export_state_token(self) -> str:
        """Export the current in-memory responses as a resumable token."""
        return encode_state_token(self.responses)

    def inject_response(self, step: str, response: Any) -> None:
        """Inject a response for one pipeline step."""
        self.responses[str(step)] = response

    def resolve(self, step: str, request: Dict[str, Any], validator: Validator) -> Any:
        payload = dict(request)
        payload["step"] = step

        if step not in self.responses:
            raise CodexTaskPending(step, payload, self.export_state_token())

        return validator(self.responses[step])
