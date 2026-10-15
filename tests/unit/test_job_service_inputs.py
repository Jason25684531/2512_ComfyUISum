from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))

from job_service import _normalize_catalog_inputs


def test_catalog_optional_text_inputs_are_forwarded():
    entry = SimpleNamespace(
        required_inputs=("prompt",),
        optional_inputs=("background",),
        input_types={"prompt": "text", "background": "text"},
        defaults={},
        choices={},
    )

    normalized, images, error = _normalize_catalog_inputs(
        entry,
        {"extra_params": {"background": "opaque"}},
        "test prompt",
    )

    assert error is None
    assert normalized == {"background": "opaque"}
    assert images == {}
