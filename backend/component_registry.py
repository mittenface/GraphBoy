import os
import json
from pathlib import Path
from typing import Dict # Import Dict for type hinting

from shared_types.component_manifest import ComponentManifest

class ComponentRegistry:
    def __init__(self) -> None:
        self.manifests: Dict[str, ComponentManifest] = {}

    def discover_components(self, components_dir_path: str | Path) -> None:
        if not isinstance(components_dir_path, Path):
            components_dir_path = Path(components_dir_path)

        if not components_dir_path.is_dir():
            print(f"Error: Components directory not found at {components_dir_path}")
            return

        for item in components_dir_path.iterdir():
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists() and manifest_path.is_file():
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest_data = json.load(f)

                        # Validate required keys by attempting to create ComponentManifest
                        try:
                            component_name = manifest_data['name']
                            component_version = manifest_data['version']
                            component_description = manifest_data['description']

                            manifest = ComponentManifest(
                                name=component_name,
                                version=component_version,
                                description=component_description
                            )
                            self.manifests[component_name] = manifest
                            # print(f"Successfully loaded manifest for component: {component_name}")
                        except KeyError as e:
                            print(f"Error: Missing key {e} in manifest {manifest_path}")
                        except Exception as e: # Catch other errors during TypedDict creation
                            print(f"Error: Could not create ComponentManifest for {manifest_path}: {e}")

                    except json.JSONDecodeError:
                        print(f"Error: Malformed JSON in manifest file: {manifest_path}")
                    except FileNotFoundError:
                        # This case should ideally not be reached due to the prior check,
                        # but included for robustness.
                        print(f"Error: Manifest file not found: {manifest_path}")
                    except Exception as e:
                        print(f"An unexpected error occurred while processing {manifest_path}: {e}")
                # else:
                    # print(f"Info: No manifest.json found in component directory: {item}")
        # print(f"Discovery complete. Found {len(self.manifests)} components.")

    def get_component_manifest(self, component_name: str) -> ComponentManifest | None:
        """
        Retrieves the manifest for a given component name.

        Args:
            component_name: The name of the component.

        Returns:
            The ComponentManifest if found, otherwise None.
        """
        return self.manifests.get(component_name)
