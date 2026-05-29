from typing import Any


class WorkflowExecutionError(Exception):
    def __init__(self, message: str, node: str | None = None, details: Any = None):
        self.node = node
        self.details = details
        super().__init__(message)


class NodeExecutionError(WorkflowExecutionError):
    def __init__(self, node: str, result: Any):
        message = f"Node '{node}' returned invalid output of type {type(result).__name__}. Expected dict."
        super().__init__(message, node=node, details={"result_type": type(result).__name__, "result_value": str(result)[:500]})


class StateValidationError(WorkflowExecutionError):
    def __init__(self, message: str, state: Any = None):
        super().__init__(message, details=state)


class MissingStateError(StateValidationError):
    def __init__(self, missing_keys: list[str], state: Any = None):
        message = f"Missing required workflow state keys: {missing_keys}"
        super().__init__(message, state={"missing_keys": missing_keys, "state": state})


class SerializationError(WorkflowExecutionError):
    def __init__(self, message: str, obj: Any = None):
        super().__init__(message, details={"obj_type": type(obj).__name__, "repr": str(obj)[:500]})
