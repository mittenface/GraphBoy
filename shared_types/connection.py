from typing import Any, Callable, Coroutine, TypedDict

class Connection(TypedDict):
    connection_id: str
    source_component_id: str
    source_port_name: str
    target_component_id: str
    target_port_name: str
    status: str
    event_name: str
    callback: Callable[[Any], Coroutine[Any, Any, None]]
