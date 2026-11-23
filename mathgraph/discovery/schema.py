import json
from dataclasses import dataclass, asdict, field
from typing import Dict, Any

@dataclass(frozen=True)
class HypothesisCandidate:
    source_node: str
    target_node: str
    hypothesis_type: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize the candidate to a JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "HypothesisCandidate":
        """Deserialize a candidate from a JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)
