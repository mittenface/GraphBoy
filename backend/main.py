import sys
from pathlib import Path

# Adjust sys.path to include the project root if this script is run directly
# This allows imports like `shared_types` and `backend.component_registry`
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from backend.component_registry import ComponentRegistry
    # For type hinting
except ImportError as e:
    print(
        f"Error importing backend modules: {e}. Make sure you are running this "
        f"script from the project root or your PYTHONPATH is set correctly."
    )
    sys.exit(1)

def initialize_backend_components():
    """
    Initializes the component registry and discovers all available components.
    This function can be expanded to set up backend routing, load modules, etc.
    """
    print("Initializing backend components...")

    registry = ComponentRegistry()

    # Assuming 'components' directory is at the project root
    components_dir = project_root / "components"

    print(f"Discovering components in: {components_dir}")
    registry.discover_components(components_dir)

    if not registry.manifests:
        print("No component manifests found.")
    else:
        print(f"Found {len(registry.manifests)} component(s):")
        for name, manifest in registry.manifests.items():
            print(f"  - {name} (Version: {manifest['version']})")
            # In a more advanced system, you might load the backend module for
            # each component here.
            # For example, by looking for a 'backend.py' in the component's
            # directory and dynamically importing it.

    # Example: Get a specific component's manifest
    chat_manifest = registry.get_component_manifest("AI Chat Interface")
    if chat_manifest:
        print(
            f"Successfully retrieved manifest for 'AI Chat Interface': "
            f"{chat_manifest['description']}"
        )
        # Here you could potentially instantiate or prepare the AI Chat Interface
        # backend if it were designed to be dynamically loaded by this main.py
        # script. For now, server.py handles its instantiation directly.

    print("Backend component initialization process complete.")
    return registry

if __name__ == "__main__":
    # This main block is for demonstration and testing of the component discovery.
    # In a full application, `server.py` or another entry point might call
    # `initialize_backend_components()`.

    print(f"Running backend main.py from: {Path(__file__).resolve()}")
    print(f"Project root determined as: {project_root}")
    print(f"Current sys.path: {sys.path}")

    registry = initialize_backend_components()

    # Further backend setup could happen here, e.g., starting a web server
    # that uses the registry to route requests to different component backends.
    # For this project, server.py is a separate simple server.
