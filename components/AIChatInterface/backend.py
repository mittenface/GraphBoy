import time # To simulate streaming

class AIChatInterfaceBackend:
    def __init__(self):
        # In a real scenario, this might load a model or set up connections.
        self.config = {}

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
            return {
                "responseText": "No input provided.",
                "responseStream": "",
                "error": False
            }

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

        # Simulate some processing delay
        time.sleep(0.5)

        # Placeholder logic: Echo the input with some modification
        response_text = f"Processed: '{user_input}' (temp={temperature}, tokens={max_tokens})"

        # Simulate a streaming response
        # In a real application, this would be more complex, yielding parts of the response.
        response_stream_data = []
        for i in range(3):
            time.sleep(0.2) # Simulate delay between stream chunks
            chunk = f"Stream chunk {i+1} for '{user_input}'\n"
            response_stream_data.append(chunk)

        # For now, we'll just concatenate the stream chunks into the main response_text
        # or return them separately if the frontend/server can handle actual streaming.
        # Let's assume for now the 'responseStream' output in manifest.json means
        # we should provide the full "streamed" content at once.
        full_stream_content = "".join(response_stream_data)

        return {
            "responseText": response_text,
            "responseStream": full_stream_content, # Or response_stream_data if handled differently
            "error": False
        }

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    backend = AIChatInterfaceBackend()
    sample_input = "Hello, AI!"
    output = backend.process_request(sample_input)
    print(f"Output for '{sample_input}':\n{output}")

    sample_input_custom = "Tell me a story."
    output_custom = backend.process_request(sample_input_custom, temperature=0.5, max_tokens=100)
    print(f"Output for '{sample_input_custom}':\n{output_custom}")
