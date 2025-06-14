class AIChatInterfaceBackend:
    def __init__(self, component_id: str, send_component_output_func):
        # In a real scenario, this might load a model or set up connections.
        self.config = {}
        self.component_id = component_id
        self.send_output_func = send_component_output_func
        print(f"AIChatInterfaceBackend {self.component_id} initialized.")

    @staticmethod
    async def mock_llm_api(user_input: str, temperature: float, max_tokens: int):
        """
        Mock LLM API function.
        """
        return {
            "responseText": f"Mock LLM response to '{user_input}' (temp={temperature}, tokens={max_tokens})",
            "responseStream": f"Mock LLM stream for '{user_input}' chunk 1\nMock LLM stream for '{user_input}' chunk 2\n",
            "error": False,
        }

    def create(self, config: dict):
        """
        Stores the configuration for the AIChatInterface.
        """
        self.config = config
        # In a real backend, you might use this config to initialize things
        print(f"AIChatInterfaceBackend {self.component_id} created with config: {self.config}")
        return {"status": "success", "message": "Configuration received."}

    async def update(self, inputs: dict):
        """
        Processes user input and emits response via send_output_func.
        """
        if 'userInput' in inputs:
            user_input = inputs['userInput']
            temperature = inputs.get('temperature', 0.7)
            max_tokens = inputs.get('max_tokens', 256)

            await self.process_request(user_input, temperature, max_tokens)
            return {"status": "success", "message": "Output will be sent via component.emitOutput"}
        else:
            await self.send_output_func(self.component_id, "error", "No input provided.")
            return {"status": "error", "message": "No input provided, error emitted."}

    async def process_request(self, user_input: str, temperature: float = 0.7, max_tokens: int = 256):
        """
        Simulates processing a user's chat input and emits the response.

        Args:
            user_input: The text input from the user.
            temperature: The temperature setting for the language model.
            max_tokens: The maximum number of tokens for the response.

        Returns:
            None (Output is sent via WebSocket using send_output_func)
        """
        print(f"AIChatInterfaceBackend {self.component_id} received request: userInput='{user_input}', temperature={temperature}, max_tokens={max_tokens}")

        # Call the mock LLM API
        api_result = await AIChatInterfaceBackend.mock_llm_api(user_input, temperature, max_tokens)

        if api_result.get("error"):
            await self.send_output_func(self.component_id, "error", api_result["error"])
        elif api_result.get("responseStream"):
            await self.send_output_func(self.component_id, "responseStream", api_result["responseStream"])
        else:
            await self.send_output_func(self.component_id, "responseText", api_result.get("responseText", ""))

# Example Usage (for testing purposes, requires a mock send_component_output_func)
if __name__ == '__main__':
    import asyncio

    async def mock_send_output(component_id, output_name, data):
        print(f"MOCK_SEND_OUTPUT: component_id='{component_id}', output_name='{output_name}', data='{data}'")

    async def main_test():
        backend = AIChatInterfaceBackend(component_id="test-chat", send_component_output_func=mock_send_output)

        print("\n--- Test Case 1: Basic Input ---")
        sample_input = "Hello, AI!"
        response = await backend.update({"userInput": sample_input})
        print(f"Update response for '{sample_input}': {response}")

        print("\n--- Test Case 2: Custom Parameters ---")
        sample_input_custom = "Tell me a story."
        response_custom = await backend.update({
            "userInput": sample_input_custom,
            "temperature": 0.5,
            "max_tokens": 100
        })
        print(f"Update response for '{sample_input_custom}': {response_custom}")

        print("\n--- Test Case 3: No Input ---")
        response_no_input = await backend.update({})
        print(f"Update response for no input: {response_no_input}")

    asyncio.run(main_test())
