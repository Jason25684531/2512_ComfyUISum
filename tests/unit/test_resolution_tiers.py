import json
import sys
from pathlib import Path

import pytest

from shared.workflow_catalog import WorkflowCatalog

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('bad', [1.5, True, 0, -16, '1920', 1080])
def test_catalog_rejects_bad_tier_dimensions(bad):
    raw = json.loads((ROOT / 'ComfyUIworkflow/config.json').read_text(encoding='utf-8'))
    raw['_runtime']['resolution_tiers']['1080p']['16:9']['width'] = bad
    with pytest.raises(ValueError, match='positive integers'):
        WorkflowCatalog(ROOT / 'ComfyUIworkflow/config.json', ROOT / 'ComfyUIworkflow', raw)


def test_tier_injection_and_legacy_fallback(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'worker/src'))
    from workflow.runtime import parse_workflow
    for options, expected in [({}, (1024, 1024)), ({'aspect_ratio': '16:9', 'resolution': '1080p'}, (1920, 1088))]:
        workflow = parse_workflow('text_to_image', prompt='test', seed=42, **options)
        sizes = [(node['inputs'].get('width'), node['inputs'].get('height')) for node in workflow.values() if 'Latent' in node.get('class_type', '')]
        assert expected in sizes
