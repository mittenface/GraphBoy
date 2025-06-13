import unittest
from unittest.mock import patch
import sys
import os
from pathlib import Path

# Add the project root to sys.path to allow imports like 'components.AIChatInterface'
# This assumes the tests might be run from different directories or with tools that don't automatically handle it.
project_root = Path(__file__).resolve().parent.parent.parent.parent # This should point to the project root
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from components.AIChatInterface.backend import AIChatInterfaceBackend
    # Or, if you prefer using the __init__.py export:
    # from components.AIChatInterface import AIChatInterfaceBackend
except ImportError:
    print("Error: Could not import AIChatInterfaceBackend for testing. Check PYTHONPATH and project structure.")
    # Define a dummy class if import fails, so tests can at least be defined, though they will likely fail.
    class AIChatInterfaceBackend:
        def process_request(self, *args, **kwargs):
            raise ImportError("AIChatInterfaceBackend not available")

class TestAIChatInterfaceBackend(unittest.TestCase):

    def setUp(self):
        """Set up for each test method."""
        try:
            self.backend = AIChatInterfaceBackend()
        except ImportError:
            self.backend = None # Tests requiring self.backend will skip or fail

    def test_backend_instantiation(self):
        """Test if the backend can be instantiated."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")
        self.assertIsNotNone(self.backend, "Backend should be instantiable")

    def test_process_request_basic(self):
        """Test the basic processing of a request."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        user_input = "Hello Test"
        expected_response_text_part = f"Processed: '{user_input}'"
        expected_stream_part = f"Stream chunk 1 for '{user_input}'"

        result = self.backend.process_request(user_input=user_input)

        self.assertFalse(result["error"], "Error flag should be False for successful request")
        self.assertIn(expected_response_text_part, result["responseText"], "Response text does not match expected output")
        self.assertIn(expected_stream_part, result["responseStream"], "Response stream does not match expected output")

        # Check structure matches manifest (simplified)
        self.assertIn("responseText", result)
        self.assertIn("responseStream", result)
        self.assertIn("error", result)

    def test_process_request_with_params(self):
        """Test processing with temperature and max_tokens parameters."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        user_input = "Params Test"
        temperature = 0.5
        max_tokens = 100

        expected_response_text_part = f"(temp={temperature}, tokens={max_tokens})"

        result = self.backend.process_request(
            user_input=user_input,
            temperature=temperature,
            max_tokens=max_tokens
        )

        self.assertFalse(result["error"])
        self.assertIn(expected_response_text_part, result["responseText"], "Response text does not reflect custom parameters")

    def test_response_structure(self):
        """Ensure the response structure includes all defined output nodes."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        user_input = "Structure Test"
        result = self.backend.process_request(user_input=user_input)

        # As per manifest.json for AIChatInterface
        # outputs: [{"name": "responseText", "type": "text"}, {"name": "responseStream", "type": "stream"}, {"name": "error", "type": "boolean"}]
        self.assertIn("responseText", result, "Response should contain 'responseText'")
        self.assertTrue(isinstance(result["responseText"], str), "'responseText' should be a string")

        self.assertIn("responseStream", result, "Response should contain 'responseStream'")
        self.assertTrue(isinstance(result["responseStream"], str), "'responseStream' should be a string (as per current backend implementation)")

        self.assertIn("error", result, "Response should contain 'error'")
        self.assertTrue(isinstance(result["error"], bool), "'error' should be a boolean")

    # --- Tests for create and update methods ---

    def test_create_stores_config(self):
        """Test if the create method stores configuration."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        sample_config = {"model": "gpt-4", "mode": "chat"}
        # Assuming create returns a status, as implemented in the previous step
        response = self.backend.create(config=sample_config)

        self.assertEqual(self.backend.config, sample_config, "Config should be stored in self.backend.config")
        self.assertIn("status", response, "Response from create should include a status")
        self.assertEqual(response["status"], "success", "Status of create should be 'success'")

    def test_update_with_user_input(self):
        """Test update method with user input and custom parameters."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        inputs = {"userInput": "Hello AI", "temperature": 0.5, "max_tokens": 100}
        expected_response_text_part = "Processed: 'Hello AI' (temp=0.5, tokens=100)"

        result = self.backend.update(inputs=inputs)

        self.assertFalse(result["error"], "Error flag should be False for successful update")
        self.assertIn(expected_response_text_part, result["responseText"], "Response text does not match expected output")

    def test_update_with_user_input_default_params(self):
        """Test update method with user input and default temperature/max_tokens."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        inputs = {"userInput": "Just testing"}
        # Defaults are temperature=0.7, max_tokens=256 as per process_request
        expected_response_text_part = "Processed: 'Just testing' (temp=0.7, tokens=256)"

        result = self.backend.update(inputs=inputs)

        self.assertFalse(result["error"], "Error flag should be False")
        self.assertIn(expected_response_text_part, result["responseText"], "Response text does not reflect default parameters")

    def test_update_without_user_input(self):
        """Test update method when no userInput is provided."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        inputs = {"some_other_param": "value"}
        expected_response = {
            "responseText": "No input provided.",
            "responseStream": "",
            "error": False
        }

        result = self.backend.update(inputs=inputs)
        self.assertEqual(result, expected_response, "Response should be the default when no userInput is provided")

    @patch.object(AIChatInterfaceBackend, 'process_request')
    def test_update_passes_all_params_to_process_request(self, mock_process_request):
        """Test that update correctly calls process_request with all parameters."""
        if self.backend is None:
            self.skipTest("AIChatInterfaceBackend could not be imported.")

        # Configure the mock to return a specific structure to prevent TypeErrors if update tries to access keys
        mock_process_request.return_value = {"responseText": "", "responseStream": "", "error": False}

        inputs = {"userInput": "Test", "temperature": 0.1, "max_tokens": 50}
        self.backend.update(inputs=inputs)

        mock_process_request.assert_called_once_with("Test", 0.1, 50)

if __name__ == '__main__':
    # This allows running the tests directly from this file
    print(f"Running tests from: {Path(__file__).resolve()}")
    print(f"Project root for test: {project_root}")
    print(f"sys.path for test: {sys.path}")
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
