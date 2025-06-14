import os
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
    Subclasses should implement methods like update, get_state, get_component_id, etc.
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
        self.event_bus = event_bus # Added
        logger.info(f"ComponentRegistry initialized {'with' if event_bus else 'without'} EventBus.") # Added logging

    def discover_components(self, components_dir_path: str | Path) -> None:
        if not isinstance(components_dir_path, Path):
            components_dir_path = Path(components_dir_path)

        if not components_dir_path.is_dir():
            logger.error(f"Components directory not found at {components_dir_path}") # Changed to logger
            return

        logger.info(f"Starting component discovery in directory: {components_dir_path}") # Added logging

        for item in components_dir_path.iterdir():
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists() and manifest_path.is_file():
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest_data = json.load(f)

                        # Validate required keys by attempting to create ComponentManifest
                        # try:
                        component_name = manifest_data['name']
                        manifest: ComponentManifest = manifest_data
                        self.manifests[component_name] = manifest
                        logger.debug(f"Successfully loaded manifest for component: {component_name} from {manifest_path}") # Changed to logger

                        # Dynamically load and instantiate component backend
                        try:
                            module_name = f"components.{item.name}.backend" # Assuming item.name is the component's directory name
                            class_name = manifest_data.get("backend_class", f"{item.name.capitalize()}Backend") # Use manifest or derive

                            module = importlib.import_module(module_name)
                            component_class = getattr(module, class_name)

                            init_kwargs = {}
                            if self.event_bus:
                                init_kwargs["event_bus"] = self.event_bus

                            # Check if 'settings' is expected by the constructor (optional)
                            # This requires more advanced introspection or a convention
                            # For now, only pass event_bus if it's defined.

                            self.instances[component_name] = component_class(**init_kwargs)
                            logger.info(f"Successfully instantiated backend for component: {component_name} (Class: {class_name})") # Changed to logger
                        except ImportError:
                            logger.error(f"Could not import backend module {module_name} for component {component_name}", exc_info=True) # Changed to logger
                        except AttributeError:
                            logger.error(f"Could not find class {class_name} in module {module_name} for component {component_name}", exc_info=True) # Changed to logger
                        except Exception as e:
                            logger.error(f"Could not instantiate backend for component {component_name}: {e}", exc_info=True) # Changed to logger

                    except json.JSONDecodeError:
                        logger.error(f"Malformed JSON in manifest file: {manifest_path}", exc_info=True) # Changed to logger
                    except FileNotFoundError:
                        logger.error(f"Manifest file not found: {manifest_path}", exc_info=True) # Changed to logger
                    except KeyError as e:
                        logger.error(f"Missing key 'name' in manifest {manifest_path}: {e}", exc_info=True) # Changed to logger
                    except Exception as e:
                        logger.error(f"An unexpected error occurred while processing {manifest_path}: {e}", exc_info=True) # Changed to logger
                else:
                    logger.debug(f"No manifest.json found in component directory: {item}, skipping.") # Added logging
        logger.info(f"Component discovery complete. Found {len(self.manifests)} manifests and instantiated {len(self.instances)} components.") # Changed to logger

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
            logger.warning(f"Component '{name}' is being re-registered.") # Changed to logger

        self.instances[name] = instance

        # Optionally, create a basic manifest entry if other parts of the system rely on it.
        if name not in self.manifests:
            self.manifests[name] = {
                "name": name,
                "version": "manual", # Placeholder version
                "description": f"Manually registered component: {component_class.__name__}",
                # Add other fields if your ComponentManifest type expects them
            }
        logger.info(f"Component '{name}' (Class: {component_class.__name__}) registered manually with instance {instance}.") # Changed to logger
