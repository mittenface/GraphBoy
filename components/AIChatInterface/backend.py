from backend.utils import emit

class AIChatInterfaceBackend:
    def __init__(self):
        # In a real scenario, this might load a model or set up connections.
        self.config = {}

    @staticmethod
    def mock_llm_api(user_input: str, temperature: float, max_tokens: int):
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
        print(f"AIChatInterfaceBackend created with config: {self.config}")
        return {"status": "success", "message": "Configuration received."}

    def update(self, inputs: dict):
        """
        Processes user input and returns a response.
        """
        if 'userInput' in inputs:
            user_input = inputs['userInput']
            # Get temperature and max_tokens from inputs, with defaults from process_request's signature
            # However, since process_request has defaults, we can just pass them if they exist,
            # or let process_request handle the defaults if they don't.
            temperature = inputs.get('temperature', 0.7)
            max_tokens = inputs.get('max_tokens', 256)

            # Potentially use self.config here if needed for process_request
            # For example: self.process_request(user_input, self.config.get('temperature', 0.7), ...)
            # But for now, let's stick to the prompt's direct instructions.
            return self.process_request(user_input, temperature, max_tokens)
        else:
            return emit("responseText", "No input provided.")

    def process_request(self, user_input: str, temperature: float = 0.7, max_tokens: int = 256):
        """
        Simulates processing a user's chat input and generating a response.

        Args:
            user_input: The text input from the user.
            temperature: The temperature setting for the language model.
            max_tokens: The maximum number of tokens for the response.

        Returns:
            A dictionary containing the responseText, responseStream, and error status.
        """
        print(f"Received request: userInput='{user_input}', temperature={temperature}, max_tokens={max_tokens}")

        # Call the mock LLM API
        api_result = AIChatInterfaceBackend.mock_llm_api(user_input, temperature, max_tokens)

        if api_result.get("error"):
            # If 'error' field is present and truthy (e.g., a non-empty string or True)
            return emit("error", api_result["error"])
        elif api_result.get("responseStream"):
            # If there's stream data, prioritize it.
            # This will result in responseText being empty unless mock_llm_api also includes it in the stream.
            return emit("responseStream", api_result["responseStream"])
        else:
            # Default to responseText if no error and no stream.
            return emit("responseText", api_result.get("responseText", "")) # Use .get for safety

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    backend = AIChatInterfaceBackend()
    sample_input = "Hello, AI!"
    output = backend.process_request(sample_input)
    print(f"Output for '{sample_input}':\n{output}")

    sample_input_custom = "Tell me a story."
    output_custom = backend.process_request(sample_input_custom, temperature=0.5, max_tokens=100)
    print(f"Output for '{sample_input_custom}':\n{output_custom}")
