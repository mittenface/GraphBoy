from typing import TypedDict, List, Dict, Any, Union

# Define a type for individual input/output nodes
class Node(TypedDict, total=False):
    name: str
    type: str
    min: Union[int, float]
    max: Union[int, float]
    default: Any

class Nodes(TypedDict):
    inputs: List[Node]
    outputs: List[Node]

class ComponentManifest(TypedDict):
    name: str
    version: str
    description: str
    nodes: Nodes
