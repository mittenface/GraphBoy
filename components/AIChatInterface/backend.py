# components/AIChatInterface/backend.py
import asyncio # Added for potential async operations in future event handlers
import logging
from typing import Callable, Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.event_bus import EventBus # For type hinting

logger = logging.getLogger(__name__)

class AIChatInterfaceBackend:
    def __init__(self, component_id: str, send_component_output_func: Callable[..., Any], event_bus: 'EventBus | None' = None, **kwargs: Any):
        self.config: Dict[str, Any] = {}
        self.component_id = component_id
        self.send_output_func = send_component_output_func
        self.event_bus = event_bus # Store the event_bus instance

        # Log the presence or absence of the event bus
        if self.event_bus:
            logger.info(f"AIChatInterfaceBackend '{self.component_id}' initialized with EventBus.")
            # Example: Subscribe to an event (actual event_type and handler would depend on application needs)
            # asyncio.create_task(self.event_bus.subscribe("some_system_event", self.handle_system_event))
        else:
            logger.info(f"AIChatInterfaceBackend '{self.component_id}' initialized WITHOUT EventBus.")

    # Placeholder for a potential event handler
    # async def handle_system_event(self, event_data: Any):
    #     logger.info(f"Component '{self.component_id}' received system_event: {event_data}")
    #     # Potentially interact with the component's state or send output

    @staticmethod
    async def mock_llm_api(user_input: str, temperature: float, max_tokens: int):
        logger.debug(f"mock_llm_api called with: user_input='{user_input}', temperature={temperature}, max_tokens={max_tokens}")
        return {
            "responseText": f"Mock LLM response to '{user_input}' (temp={temperature}, tokens={max_tokens})",
            "responseStream": f"Mock LLM stream for '{user_input}' chunk 1\nMock LLM stream for '{user_input}' chunk 2\n",
            "error": None, # Changed from False to None for consistency, assuming error would contain a message string
        }

    def create(self, config: dict):
        self.config = config
        logger.info(f"AIChatInterfaceBackend '{self.component_id}' created/configured with: {self.config}")
        # Example: Publish an event after configuration (if useful)
        # if self.event_bus:
        #    asyncio.create_task(self.event_bus.publish(f"component.{self.component_id}.configured", {"config": self.config}))
        return {"status": "success", "message": "Configuration received."}

    async def update(self, inputs: dict):
        logger.debug(f"AIChatInterfaceBackend '{self.component_id}' update called with inputs: {inputs}")
        if 'userInput' in inputs:
            user_input = inputs['userInput']
            temperature = inputs.get('temperature', 0.7)
            max_tokens = inputs.get('max_tokens', 256)

            await self.process_request(user_input, temperature, max_tokens)
            return {"status": "success", "message": "Output processing initiated, will be sent via component.emitOutput"}
        else:
            error_message = "No userInput provided in inputs."
            logger.warning(f"AIChatInterfaceBackend '{self.component_id}': {error_message}")
            # It's good practice to also inform the client if an error occurs due to bad input
            await self.send_output_func(self.component_id, "error", {"message": error_message})
            return {"status": "error", "message": error_message} # Return error status to JSON-RPC caller

    async def process_request(self, user_input: str, temperature: float = 0.7, max_tokens: int = 256):
        logger.info(f"AIChatInterfaceBackend '{self.component_id}' processing request: userInput='{user_input}', temp={temperature}, tokens={max_tokens}")

        api_result = await AIChatInterfaceBackend.mock_llm_api(user_input, temperature, max_tokens)

        if api_result.get("error"):
            logger.error(f"AIChatInterfaceBackend '{self.component_id}' encountered an API error: {api_result['error']}")
            await self.send_output_func(self.component_id, "error", {"message": api_result["error"]})
        elif api_result.get("responseStream"):
            logger.debug(f"AIChatInterfaceBackend '{self.component_id}' sending stream output.")
            await self.send_output_func(self.component_id, "responseStream", {"streamContent": api_result["responseStream"]})
        elif api_result.get("responseText") is not None: # Check for not None, as empty string is a valid response
            logger.debug(f"AIChatInterfaceBackend '{self.component_id}' sending text output.")
            await self.send_output_func(self.component_id, "responseText", {"text": api_result["responseText"]})
        else:
            logger.warning(f"AIChatInterfaceBackend '{self.component_id}': API result had no error, stream, or text. Result: {api_result}")
            # Optionally send a generic error or a "no_response" message
            await self.send_output_func(self.component_id, "error", {"message": "No response generated by the LLM."})

    async def process_input(self, port_name: str, data: Any):
        """
        Processes data received on a specific input port of the component.
        """
        logger.info(f"AIChatInterfaceBackend '{self.component_id}' received data on port '{port_name}'. Data: {data}")

        if port_name == "textPrompt":
            if isinstance(data, str):
                # Assuming data is the raw text input for "textPrompt"
                # Using default values for temperature and max_tokens from process_request
                await self.process_request(user_input=data)
                logger.debug(f"AIChatInterfaceBackend '{self.component_id}': 'textPrompt' processed using received string data.")
            elif isinstance(data, dict) and 'text' in data and isinstance(data['text'], str):
                # If data is a dict with a 'text' field, use that.
                # This provides flexibility if the event system sends structured data.
                user_input = data['text']
                # Could potentially extract other params like temperature from data if available
                # temperature = data.get('temperature', 0.7)
                # max_tokens = data.get('max_tokens', 256)
                await self.process_request(user_input=user_input)
                logger.debug(f"AIChatInterfaceBackend '{self.component_id}': 'textPrompt' processed using 'text' field from received dict data.")
            else:
                logger.warning(f"AIChatInterfaceBackend '{self.component_id}': Received data for 'textPrompt' is not a string or a dict with a 'text' field. Data type: {type(data)}. Data: {data}")
                await self.send_output_func(self.component_id, "error", {"message": f"Invalid data type for textPrompt: {type(data)}"})
        else:
            logger.warning(f"AIChatInterfaceBackend '{self.component_id}': Received data for unrecognized port '{port_name}'.")
            # Optionally, send an error back or handle other ports if they exist
            # await self.send_output_func(self.component_id, "error", {"message": f"Unrecognized input port: {port_name}"})


if __name__ == '__main__':
    import asyncio

    # Setup basic logging for the __main__ example
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    async def mock_send_output(component_id, output_name, data):
        logger.info(f"MOCK_SEND_OUTPUT: component_id='{component_id}', output_name='{output_name}', data='{data}'")

    # Mock EventBus for standalone testing
    class MockEventBus:
        async def subscribe(self, event_type, callback):
            logger.debug(f"MockEventBus: {callback.__name__} subscribed to {event_type}")
        async def publish(self, event_type, *args, **kwargs):
            logger.debug(f"MockEventBus: Published {event_type} with {args}, {kwargs}")

    async def main_test():
        mock_bus = MockEventBus()
        # Pass component_id, send_output_func, and the event_bus
        backend = AIChatInterfaceBackend(
            component_id="test-chat-001",
            send_component_output_func=mock_send_output,
            event_bus=mock_bus
        )
        backend_no_bus = AIChatInterfaceBackend(
            component_id="test-chat-002",
            send_component_output_func=mock_send_output
            # event_bus is omitted, will default to None
        )


        logger.info("\n--- Test Case 1: Basic Input (with EventBus) ---")
        await backend.update({"userInput": "Hello, AI!"})

        logger.info("\n--- Test Case 2: Custom Parameters (with EventBus) ---")
        await backend.update({"userInput": "Tell me a story.", "temperature": 0.5, "max_tokens": 100})

        logger.info("\n--- Test Case 3: No Input (with EventBus) ---")
        await backend.update({})

        logger.info("\n--- Test Case 4: Basic Input (NO EventBus) ---")
        await backend_no_bus.update({"userInput": "Hello again, AI!"})


    asyncio.run(main_test())
