import uuid
from typing import Any, Dict

def generate_unique_id() -> str:
    """Generates a unique string identifier."""
    return str(uuid.uuid4())

def emit(output_name: str, value: Any) -> Dict[str, Any]:
    """
    Creates a dictionary for component output.

    Args:
        output_name: The name of the output to populate.
                     Valid names are "responseText", "responseStream", "error".
        value: The value to assign to the specified output_name.

    Returns:
        A dictionary with responseText, responseStream, and error keys.
    """
    response = {
        "responseText": "",
        "responseStream": "",
        "error": False,
    }

    if output_name in response:
        response[output_name] = value
    else:
        # Optionally, handle unknown output_name, e.g., by logging a warning
        # or raising an error, or simply ignoring it.
        # For now, we'll assume valid inputs as per the intended use.
        print(f"Warning: Unknown output_name '{output_name}' provided to emit function.")

    return response
