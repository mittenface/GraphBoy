import json
import importlib
import logging # Added
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING # Added TYPE_CHECKING

if TYPE_CHECKING:
    from backend.event_bus import EventBus # Added for type hinting

# Using a placeholder for ComponentManifest as shared_types is not available
ComponentManifest = Dict[str, Any]

logger = logging.getLogger(__name__) # Added

class ComponentInterface:
    """
    A base interface for components.
    Subclasses should implement methods like update, get_state,
    get_component_id, etc.
    """
    def update(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Processes inputs and updates the component's state."""
        raise NotImplementedError

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state of the component."""
        raise NotImplementedError

    def get_component_id(self) -> str:
        """Returns the unique identifier of the component instance."""
        raise NotImplementedError

class ComponentRegistry:
    def __init__(self, event_bus: 'EventBus | None' = None) -> None: # Modified
        self.manifests: Dict[str, ComponentManifest] = {}
        self.instances: Dict[str, Any] = {}
        # Added for port details
        self.port_details: Dict[str, Dict[str, Dict[str, str]]] = {}
        self.event_bus = event_bus # Added
        # Added logging
        logger.info(
            "ComponentRegistry initialized %s EventBus.",
            "with" if event_bus else "without"
        )

    def discover_components(self, components_dir_path: str | Path) -> None:
        if not isinstance(components_dir_path, Path):
            components_dir_path = Path(components_dir_path)

        if not components_dir_path.is_dir():
            # Changed to logger
            logger.error(
                "Components directory not found at %s", components_dir_path
            )
            return
        # Added logging
        logger.info("Starting component discovery in directory: %s",
                    components_dir_path)

        for item in components_dir_path.iterdir():
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists() and manifest_path.is_file():
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest_data = json.load(f)

                        # Validate required keys by attempting to create
                        # ComponentManifest
                        # try:
                        component_name = manifest_data['name']
                        manifest: ComponentManifest = manifest_data
                        self.manifests[component_name] = manifest
                        # Changed to logger
                        logger.debug("Loaded manifest: %s from %s",
                                     component_name, manifest_path)

                        # Parse and store port details
                        self.port_details[component_name] = {}
                        nodes = manifest_data.get("nodes", {})
                        for port_type_str in ["inputs", "outputs"]:
                            if port_type_str in nodes:
                                for port_info in nodes[port_type_str]:
                                    port_name = port_info.get("name")
                                    if port_name:
                                        details = {
                                            "name": port_name,
                                            "type": port_type_str[:-1],
                                            "data_type": port_info.get(
                                                "type", "unknown"
                                            )
                                        }
                                        self.port_details[component_name][port_name] = details
                        # Dynamically load and instantiate component backend
                        try:
                            # Assuming item.name is the component's directory
                            # name
                            module_name = f"components.{item.name}.backend"
                            # Use manifest or derive
                            class_name = manifest_data.get(
                                "backend_class",
                                f"{item.name.capitalize()}Backend"
                            )

                            module = importlib.import_module(module_name)
                            component_class = getattr(module, class_name)

                            # Use component_name as component_id
                            init_kwargs = {
                                "component_id": component_name,
                                "send_component_output_func": (
                                    lambda _id, _port, _data: logger.debug(
                                        "Placeholder: %s port %s data %s",
                                        _id, _port, _data
                                    )
                                )
                            }
                            if self.event_bus:
                                init_kwargs["event_bus"] = self.event_bus

                            # Check if 'settings' is expected by the constructor
                            # (optional). This requires more advanced
                            # introspection or a convention. For now, only pass
                            # event_bus if it's defined.

                            self.instances[component_name] = component_class(
                                **init_kwargs
                            )
                            # Changed to logger
                            logger.info(
                                "Instantiated backend: %s (Class: %s)",
                                component_name, class_name
                            )
                        # Changed to logger
                        except ImportError:
                            logger.error(
                                "ImportError for %s of %s",
                                module_name, component_name, exc_info=True
                            )
                        # Changed to logger
                        except AttributeError:
                            logger.error(
                                "AttributeError for %s in %s of %s",
                                class_name, module_name, component_name,
                                exc_info=True
                            )
                        # Changed to logger
                        except Exception as e:
                            logger.error(
                                "Exception instantiating %s: %s",
                                component_name, e, exc_info=True
                            )
                    # Changed to logger
                    except json.JSONDecodeError:
                        logger.error("Malformed JSON: %s",
                                     manifest_path, exc_info=True)
                    # Changed to logger
                    except FileNotFoundError:
                        logger.error("Manifest not found: %s",
                                     manifest_path, exc_info=True)
                    # Changed to logger
                    except KeyError as e:
                        logger.error("Missing key 'name' in %s: %s",
                                     manifest_path, e, exc_info=True)
                    # Changed to logger
                    except Exception as e:
                        logger.error(
                            "Unexpected error processing %s: %s",
                            manifest_path, e, exc_info=True
                        )
                # Added logging
                else:
                    logger.debug("No manifest.json in %s, skipping.", item)
        # Changed to logger
        logger.info(
            "Discovery complete. Found %d manifests, "
            "instantiated %d components.",
            len(self.manifests), len(self.instances)
        )

    def get_port_details(self, component_name: str,
                         port_name: str) -> Dict[str, str] | None:
        """
        Retrieves the details of a specific port for a given component.

        Args:
            component_name: The name of the component.
            port_name: The name of the port.

        Returns:
            A dictionary containing the port details (name, type, data_type)
            if found, otherwise None.
        """
        return self.port_details.get(component_name, {}).get(port_name)

    def get_component_manifest(self, component_name: str) -> ComponentManifest | None:
        """
        Retrieves the manifest for a given component name.

        Args:
            component_name: The name of the component.

        Returns:
            The ComponentManifest if found, otherwise None.
        """
        return self.manifests.get(component_name)

    def get_component_instance(self, component_name: str) -> Any | None:
        """
        Retrieves the backend instance for a given component name.

        Args:
            component_name: The name of the component.

        Returns:
            The component instance if found, otherwise None.
        """
        return self.instances.get(component_name)

    def register_component(self, name: str, component_class: type, instance: Any) -> None:
        """
        Manually registers a component class and its instance.
        """
        if name in self.instances:
            # Changed to logger
            logger.warning(f"Component '{name}' is being re-registered.")

        self.instances[name] = instance

        # Optionally, create a basic manifest entry if other parts of the system rely on it.
        if name not in self.manifests:
            self.manifests[name] = {
                "name": name,
                "version": "manual", # Placeholder version
                "description": (
                    f"Manually registered component: {component_class.__name__}"
                ),
                # Add other fields if your ComponentManifest type expects them
            }
        # Changed to logger
        logger.info(
            "Component '%s' (Class: %s) registered manually with instance %s.",
            name, component_class.__name__, instance
        )

    def clear(self) -> None:
        """
        Clears all registered components, manifests, instances, and port details.
        Useful for testing or resetting state.
        """
        self.manifests.clear()
        self.instances.clear()
        self.port_details.clear()
        logger.info("ComponentRegistry cleared.")
