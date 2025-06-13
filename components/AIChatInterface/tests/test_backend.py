import unittest
import sys
from pathlib import Path

# Add the project root to sys.path to allow imports like 'components.AIChatInterface'
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from components.AIChatInterface.backend import AIChatInterfaceBackend

class TestAIChatInterfaceBackend(unittest.TestCase):
    def setUp(self):
        self.backend = AIChatInterfaceBackend()
        # self.backend.create({}) # No specific config needed for these tests

    def test_backend_instantiation(self):
        """Test if the backend can be instantiated."""
        self.assertIsNotNone(self.backend, "Backend should be instantiable")

    def test_create_stores_config(self):
        """Test if the create method stores configuration."""
        sample_config = {"model": "test-model", "setting": "test-setting"}
        response = self.backend.create(config=sample_config)
        self.assertEqual(self.backend.config, sample_config, "Config should be stored in self.backend.config")
        self.assertIn("status", response)
        self.assertEqual(response["status"], "success")

    def test_update_with_mock_llm_defaults(self):
        """Test update method with mock LLM and default parameters."""
        user_input = "Hello with defaults"
        # Defaults from process_request signature are temp=0.7, max_tokens=256
        # These are passed by update() to process_request(), then to mock_llm_api()
        expected_response_text = f"Mock LLM response to '{user_input}' (temp=0.7, tokens=256)"
        expected_response_stream = f"Mock LLM stream for '{user_input}' chunk 1\nMock LLM stream for '{user_input}' chunk 2\n"

        response = self.backend.update({"userInput": user_input})

        self.assertFalse(response["error"])
        self.assertEqual(response["responseText"], expected_response_text)
        self.assertEqual(response["responseStream"], expected_response_stream)

    def test_update_with_mock_llm_custom_params(self):
        """Test update method with mock LLM and custom parameters."""
        user_input = "Hello with custom params"
        temp = 0.5
        tokens = 100
        expected_response_text = f"Mock LLM response to '{user_input}' (temp={temp}, tokens={tokens})"
        expected_response_stream = f"Mock LLM stream for '{user_input}' chunk 1\nMock LLM stream for '{user_input}' chunk 2\n"

        response = self.backend.update({
            "userInput": user_input,
            "temperature": temp,
            "max_tokens": tokens
        })

        self.assertFalse(response["error"])
        self.assertEqual(response["responseText"], expected_response_text)
        self.assertEqual(response["responseStream"], expected_response_stream)

    def test_update_no_input(self):
        """Test update method when no userInput is provided."""
        response = self.backend.update({})
        self.assertFalse(response["error"]) # As per current update logic for no input
        self.assertEqual(response["responseText"], "No input provided.")
        self.assertEqual(response["responseStream"], "")

    def test_response_structure_after_update(self):
        """Ensure the response structure from update matches manifest output nodes."""
        user_input = "Structure Test via Update"
        response = self.backend.update({"userInput": user_input})

        self.assertIn("responseText", response)
        self.assertTrue(isinstance(response["responseText"], str))

        self.assertIn("responseStream", response)
        self.assertTrue(isinstance(response["responseStream"], str))

        self.assertIn("error", response)
        self.assertTrue(isinstance(response["error"], bool))

if __name__ == '__main__':
    unittest.main()
