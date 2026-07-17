from types import SimpleNamespace

from worker.src.workflow.observability import WorkflowAdapter


def test_adapter_extracts_model_and_node_stage():
    adapter = WorkflowAdapter(SimpleNamespace(observability={
        "model_source": {"node_id": "4", "input": "ckpt_name"},
        "important_nodes": [{"node_id": "4", "stage": "model_load"}],
        "output": {"node_ids": ["9"]},
    }))
    workflow = {"4": {"class_type": "CheckpointLoader", "inputs": {"ckpt_name": "model.safetensors"}}}
    assert adapter.model(workflow) == "model.safetensors"
    assert adapter.node(workflow, "4") == {"node_id": "4", "node_type": "CheckpointLoader", "stage": "model_load"}
    assert adapter.expected_output_nodes() == ("9",)
