"""Veo3 workflow trimming helpers."""

from workflow.node_utils import safe_print as print
from workflow.node_utils import set_node_input_value


def trim_veo3_workflow(workflow: dict, image_files: dict) -> dict:
    valid_shots = []
    for i in range(5):
        shot_key = f"shot_{i}"
        if shot_key in image_files and image_files[shot_key]:
            valid_shots.append(i)

    shot_count = len(valid_shots)
    print(f"[Parser] Veo3 trim: detected {shot_count} shot(s): {valid_shots}")

    if shot_count == 0:
        print("[Parser] Warning: no shot images provided; keeping original workflow")
        return workflow

    if shot_count == 5:
        print("[Parser] All 5 shots provided; keeping original workflow")
        return workflow

    shot_nodes = {
        0: {"load": "6", "gen": "10"},
        1: {"load": "20", "gen": "21"},
        2: {"load": "30", "gen": "31"},
        3: {"load": "40", "gen": "41"},
        4: {"load": "50", "gen": "51"},
    }

    nodes_to_remove = []
    for i in range(5):
        if i not in valid_shots:
            nodes = shot_nodes[i]
            nodes_to_remove.extend([nodes["load"], nodes["gen"]])
            print(f"[Parser] Removing Shot {i + 1} nodes: {nodes}")

    for node_id in nodes_to_remove:
        if node_id in workflow:
            del workflow[node_id]

    for node_id in ["100", "101", "102", "103"]:
        if node_id in workflow:
            del workflow[node_id]

    valid_gen_nodes = [shot_nodes[i]["gen"] for i in valid_shots]
    print(f"[Parser] Remaining generator nodes: {valid_gen_nodes}")

    if shot_count == 1:
        if "110" in workflow:
            set_node_input_value(
                workflow,
                "110",
                "images",
                [valid_gen_nodes[0], 0],
                "Single shot output link",
            )
            print(f"[Parser] Single shot mode: node 110 linked to {valid_gen_nodes[0]}")
    else:
        batch_node_id = 100

        workflow[str(batch_node_id)] = {
            "inputs": {
                "image1": [valid_gen_nodes[0], 0],
                "image2": [valid_gen_nodes[1], 0],
            },
            "class_type": "ImageBatch",
            "_meta": {"title": "Batch Images (Dynamic)"},
        }
        print(f"[Parser] Created ImageBatch {batch_node_id}: {valid_gen_nodes[0]} + {valid_gen_nodes[1]}")

        for i in range(2, shot_count):
            prev_batch_id = str(batch_node_id)
            batch_node_id += 1

            workflow[str(batch_node_id)] = {
                "inputs": {
                    "image1": [prev_batch_id, 0],
                    "image2": [valid_gen_nodes[i], 0],
                },
                "class_type": "ImageBatch",
                "_meta": {"title": f"Batch Images (Dynamic {i})"},
            }
            print(f"[Parser] Created ImageBatch {batch_node_id}: {prev_batch_id} + {valid_gen_nodes[i]}")

        if "110" in workflow:
            set_node_input_value(
                workflow,
                "110",
                "images",
                [str(batch_node_id), 0],
                "ImageBatch final output link",
            )
            print(f"[Parser] Node 110 linked to final ImageBatch: {batch_node_id}")

    return workflow
