import unittest
from unittest.mock import AsyncMock
import sys
from pathlib import Path
# Required for IsolatedAsyncioTestCase
from components.AIChatInterface.backend import AIChatInterfaceBackend # Moved to top

# Add the project root to sys.path to allow imports like
# 'components.AIChatInterface'
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Inherit from IsolatedAsyncioTestCase
class TestAIChatInterfaceBackend(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self): # Renamed from setUp and made async
        self.mock_send_output_func = AsyncMock() # AsyncMock for async function
        self.test_component_id = "test-chat-interface"
        self.backend = AIChatInterfaceBackend(
            component_id=self.test_component_id,
            send_component_output_func=self.mock_send_output_func
        )
        # self.backend.create({}) # No specific config needed for these tests

    async def test_backend_instantiation(self):
        """Test if the backend can be instantiated."""
        self.assertIsNotNone(self.backend, "Backend should be instantiable")
        self.assertEqual(self.backend.component_id, self.test_component_id)
        self.assertEqual(self.backend.send_output_func, self.mock_send_output_func)

    async def test_create_stores_config(self):
        """Test if the create method stores configuration."""
        sample_config = {"model": "test-model", "setting": "test-setting"}
        # create is not async, so no await needed
        response = self.backend.create(config=sample_config)
        self.assertEqual(self.backend.config, sample_config,
                         "Config should be stored in self.backend.config")
        self.assertIn("status", response)
        self.assertEqual(response["status"], "success")

    async def test_update_with_mock_llm_defaults_emits_stream(self):
        """Test update method emits responseStream by default."""
        user_input = "Hello with defaults"
        # Defaults from process_request signature are temp=0.7, max_tokens=256
        expected_response_stream_content = (
            f"Mock LLM stream for '{user_input}' chunk 1\n"
            f"Mock LLM stream for '{user_input}' chunk 2\n"
        )

        response = await self.backend.update({"userInput": user_input})

        self.mock_send_output_func.assert_called_once_with(
            self.test_component_id,
            "responseStream", # Default mock_llm_api provides responseStream
            {"streamContent": expected_response_stream_content}
        )
        self.assertEqual(response, {"status": "success",
                                     "message": "Output processing initiated, will be sent via component.emitOutput"})

    async def test_update_with_mock_llm_custom_params_emits_stream(self):
        """Test update method with custom params emits responseStream."""
        user_input = "Hello with custom params"
        temp = 0.5
        tokens = 100
        expected_response_stream_content = (
            f"Mock LLM stream for '{user_input}' chunk 1\n"
            f"Mock LLM stream for '{user_input}' chunk 2\n"
        )

        response = await self.backend.update({
            "userInput": user_input,
            "temperature": temp,
            "max_tokens": tokens
        })

        self.mock_send_output_func.assert_called_once_with(
            self.test_component_id,
            "responseStream", # Default mock_llm_api provides responseStream
            {"streamContent": expected_response_stream_content}
        )
        self.assertEqual(response, {"status": "success",
                                     "message": "Output processing initiated, will be sent via component.emitOutput"})

    async def test_update_no_input_emits_error(self):
        """Test update method when no userInput is provided emits an error."""
        response = await self.backend.update({})

        self.mock_send_output_func.assert_called_once_with(
            self.test_component_id,
            "error",
            {"message": "No userInput provided in inputs."}
        )
        self.assertEqual(response, {"status": "error",
                                     "message": "No userInput provided in inputs."})

    async def test_update_emits_error_on_llm_error(self):
        """Test update method emits error if mock_llm_api returns an error."""
        user_input = "Trigger error"
        # Temporarily patch mock_llm_api to return an error
        original_mock_llm_api = AIChatInterfaceBackend.mock_llm_api
        try:
            async def mock_llm_api_error_version(*args, **kwargs):
                return {"error": "Simulated LLM error"}
            AIChatInterfaceBackend.mock_llm_api = mock_llm_api_error_version

            response = await self.backend.update({"userInput": user_input})

            self.mock_send_output_func.assert_called_once_with(
                self.test_component_id,
                "error",
                {"message": "Simulated LLM error"}
            )
            self.assertEqual(response, {"status": "success",
                                         "message": "Output processing initiated, will be sent via component.emitOutput"})
        finally:
            # Restore original mock_llm_api
            AIChatInterfaceBackend.mock_llm_api = original_mock_llm_api


if __name__ == '__main__':
    unittest.main()
