import unittest
import sys
from pathlib import Path

# Add repository root to sys.path to allow direct imports of modules
# Assuming the script is run from the repository root or the tests directory
# Adjust if the execution context is different.
# For `python -m unittest backend.tests.test_component_registry` from root,
# Python automatically handles the paths for `backend.` and `shared_types.`
# However, to be robust for other execution methods, we can add this.
# current_dir = Path(__file__).parent
# repo_root = current_dir.parent.parent # Assuming tests is in backend/tests
# sys.path.insert(0, str(repo_root))


from backend.component_registry import ComponentRegistry

# Define the path to the components directory relative to this test file
# Or, more robustly, relative to the assumed repository root.
# If tests are run from repo root:
COMPONENTS_DIR = Path("components")

class TestComponentRegistry(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures, if any."""
        self.registry = ComponentRegistry()
        # Ensure the components directory path is correct.
        # If this test file is backend/tests/test_component_registry.py,
        # and components is at the root, then components_dir should be
        # resolved correctly.
        self.registry.discover_components(COMPONENTS_DIR)

    def test_discover_dummy_component(self):
        """Test that the dummy component is discovered."""
        self.assertTrue(self.registry.manifests,
                        "Manifests dictionary should not be empty.")
        self.assertIn("Dummy Component", self.registry.manifests,
                      "Dummy Component should be in manifests.")

        manifest = self.registry.manifests["Dummy Component"]
        self.assertIsNotNone(manifest,
                             "Manifest for Dummy Component should not be None.")

        # Type checking for manifest will assume it's ComponentManifest
        # but it's good to be explicit in tests.
        self.assertEqual(manifest['name'], "Dummy Component")
        self.assertEqual(manifest['version'], "1.0.0")
        self.assertEqual(manifest['description'],
                         "A dummy component for demonstration purposes.")

    def test_get_component_manifest(self):
        """Test retrieving an existing component's manifest."""
        manifest = self.registry.get_component_manifest("Dummy Component")
        self.assertIsNotNone(manifest,
                             "Should retrieve manifest for Dummy Component.")
        if manifest: # Check to satisfy type checkers and for safety
            self.assertEqual(manifest['name'], "Dummy Component")

    def test_get_missing_component_manifest(self):
        """Test retrieving a non-existent component's manifest."""
        manifest = self.registry.get_component_manifest("NonExistentComponent")
        self.assertIsNone(manifest,
                          "Should return None for a non-existent component.")

    def test_get_port_details_existing_component_input_port(self):
        """Test retrieving an existing input port for AI Chat Interface."""
        port_details = self.registry.get_port_details("AI Chat Interface",
                                                      "userInput")
        self.assertIsNotNone(
            port_details,
            "Should retrieve port details for AI Chat Interface's userInput."
        )
        if port_details: # For type checker
            self.assertEqual(port_details['name'], "userInput")
            self.assertEqual(port_details['type'], "input")
            self.assertEqual(port_details['data_type'], "text")

    def test_get_port_details_existing_component_output_port(self):
        """Test retrieving an existing output port for AI Chat Interface."""
        port_details = self.registry.get_port_details("AI Chat Interface",
                                                      "responseText")
        self.assertIsNotNone(
            port_details,
            "Should retrieve port details for AI Chat Interface's responseText."
        )
        if port_details: # For type checker
            self.assertEqual(port_details['name'], "responseText")
            self.assertEqual(port_details['type'], "output")
            self.assertEqual(port_details['data_type'], "text")

    def test_get_port_details_non_existent_port(self):
        """Test retrieving a non-existent port for an existing component."""
        port_details = self.registry.get_port_details("AI Chat Interface",
                                                      "nonExistentPort")
        self.assertIsNone(port_details,
                          "Should return None for a non-existent port.")

    def test_get_port_details_non_existent_component(self):
        """Test retrieving a port for a non-existent component."""
        port_details = self.registry.get_port_details("NonExistentComponent",
                                                      "anyPort")
        self.assertIsNone(port_details,
                          "Should return None for a non-existent component.")

    def test_get_port_details_component_with_no_nodes(self):
        """Test retrieving a port for a component with no 'nodes' in its manifest."""
        # Dummy Component's manifest does not have 'nodes'.
        port_details = self.registry.get_port_details("Dummy Component", "anyPort")
        self.assertIsNone(
            port_details,
            "Should return None for a component with no port definitions."
        )

if __name__ == '__main__':
    # This allows running the tests directly from this file,
    # e.g., python backend/tests/test_component_registry.py
    # For this to work, Python needs to be able to find 'backend' and
    # 'shared_types'.
    # If run from repo root as `python -m unittest backend.tests.test_component_registry`,
    # this __main__ block is not executed.

    # A common pattern for making sure modules are found when running a test file
    # directly:
    # Get the absolute path to the project root.
    # backend/tests/test_... -> backend/ -> root
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))

    # Now re-import with the updated path if necessary, or rely on initial imports
    # if they work.
    # This is tricky because imports happen at the top.
    # The best practice is to run tests using `python -m unittest discover` or
    # similar from the root.

    unittest.main()
