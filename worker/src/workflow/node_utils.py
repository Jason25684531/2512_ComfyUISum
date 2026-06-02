"""Node lookup and mutation helpers for workflow payloads."""

import builtins
import sys

from workflow_registry import find_workflow_node


def safe_print(*args, **kwargs):
    file = kwargs.get("file", sys.stdout)
    encoding = getattr(file, "encoding", None) or "utf-8"
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    flush = kwargs.get("flush", False)
    message = sep.join(str(arg) for arg in args)
    safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
    builtins.print(safe_message, end=end, file=file, flush=flush)


print = safe_print


def safe_log_value(value) -> str:
    return ascii(value)


def get_workflow_node(workflow: dict, node_id: str):
    node = find_workflow_node(workflow, node_id)
    if not isinstance(node, dict):
        print(f"[Parser] Warning: Node {node_id} is not a dict: {type(node).__name__}")
        return None
    return node


def set_node_input_value(workflow: dict, node_id: str, input_key: str, value, label: str = "") -> bool:
    node = get_workflow_node(workflow, node_id)
    if not node:
        return False

    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        print(f"[Parser] Warning: Node {node_id} does not expose dict inputs")
        return False

    if input_key not in inputs:
        print(f"[Parser] Warning: Node {node_id} missing inputs.{input_key}")
        return False

    old_value = inputs.get(input_key)
    inputs[input_key] = value

    if label:
        print(
            f"[Parser] {label}: Node {node_id}.{input_key} = "
            f"{safe_log_value(old_value)} -> {safe_log_value(value)}"
        )
    return True


def _set_widget_prompt_value(node: dict, node_id: str, prompt_value: str, label: str, widget_keys: tuple[str, ...]) -> bool:
    widgets_values = node.get("widgets_values")
    if isinstance(widgets_values, list) and widgets_values:
        old_value = widgets_values[0]
        widgets_values[0] = prompt_value
        if label:
            print(
                f"[Parser] {label}: Node {node_id}.widgets_values[0] = "
                f"{safe_log_value(old_value)} -> {safe_log_value(prompt_value)}"
            )
        return True

    if isinstance(widgets_values, dict):
        for widget_key in widget_keys:
            if widget_key in widgets_values:
                old_value = widgets_values[widget_key]
                widgets_values[widget_key] = prompt_value
                if label:
                    print(
                        f"[Parser] {label}: Node {node_id}.widgets_values[{widget_key!r}] = "
                        f"{safe_log_value(old_value)} -> {safe_log_value(prompt_value)}"
                    )
                return True

    return False


def set_node_prompt_value(workflow: dict, node_id: str, prompt_value: str, label: str = "") -> bool:
    for input_key in ("text", "prompt", "string"):
        if set_node_input_value(workflow, node_id, input_key, prompt_value, label):
            return True

    node = get_workflow_node(workflow, node_id)
    if not node:
        return False

    if _set_widget_prompt_value(node, node_id, prompt_value, label, ("text", "prompt", "string")):
        return True

    print(f"[Parser] Warning: Node {node_id} cannot accept prompt/text/string injection")
    return False


def set_configured_prompt_value(workflow: dict, node_id: str, input_key: str, prompt_value: str, label: str = "") -> bool:
    node = find_workflow_node(workflow, node_id)
    if node is None:
        print(f"[Parser] Warning: prompt_map target node {node_id} not found")
        return False
    if not isinstance(node, dict):
        print(f"[Parser] Warning: prompt_map target node {node_id} is not a dict")
        return False

    inputs = node.get("inputs")
    if isinstance(inputs, dict) and input_key in inputs:
        old_value = inputs.get(input_key)
        inputs[input_key] = prompt_value
        if label:
            print(
                f"[Parser] prompt_map API 注入: Node {node_id}.{input_key} = "
                f"{safe_log_value(old_value)} -> {safe_log_value(prompt_value)}"
            )
        return True

    if _set_widget_prompt_value(node, node_id, prompt_value, label, (input_key, "prompt", "text", "string")):
        return True

    print(f"[Parser] Warning: prompt_map target {node_id}.{input_key} cannot be injected")
    return False
