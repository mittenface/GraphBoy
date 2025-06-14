import asyncio
import json
import websockets
import logging
import functools
from backend.component_registry import ComponentRegistry, ComponentInterface
from backend.utils import generate_unique_id

# Configure basic logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

WS_PORT = 8765

class AIChatInterfaceBackend(ComponentInterface):
    """
    A backend component that interacts with a chat model.
    """
    def __init__(self, component_id=None):
        self.component_id = component_id or generate_unique_id()
        self.state = {"status": "initialized", "history": []}
        logger.info(f"AIChatInterfaceBackend {self.component_id} initialized.")

    async def update(self, inputs: dict) -> dict:
        logger.info(f"AIChatInterfaceBackend {self.component_id} update called with inputs: {inputs}")
        user_input = inputs.get("userInput")
        # Simulate model processing
        await asyncio.sleep(0.1) # Simulate async work
        response_text = f"Mock response to: {user_input}"

        self.state["history"].append({"user": user_input, "assistant": response_text})
        self.state["status"] = "updated"

        return {
            "status": "success",
            "componentId": self.component_id,
            "responseText": response_text,
            "updatedState": self.state
        }

    def get_state(self) -> dict:
        logger.info(f"AIChatInterfaceBackend {self.component_id} get_state called.")
        return self.state

    def get_component_id(self) -> str:
        return self.component_id

# Global registry instance (assuming ComponentRegistry is thread-safe or managed appropriately)
component_registry = ComponentRegistry()

async def process_request_hook(websocket, path_from_hook: str):
    """
    Hook to capture the request path and attach it to the websocket connection object.
    This is called by websockets.serve for each new connection, before the main handler.
    """
    logger.debug(f"process_request_hook: path '{path_from_hook}' attached to connection {websocket.id}")
    websocket.actual_request_path = path_from_hook # Attach the path here

async def websocket_handler(websocket, chat_backend: AIChatInterfaceBackend, registry: ComponentRegistry):
    """
    Handles WebSocket connections and routes JSON-RPC requests.
    The 'path' argument is no longer directly here, it's accessed via websocket.actual_request_path.
    """
    path = getattr(websocket, 'actual_request_path', '/') # Get path from the connection object
    logger.info(f"Client connected from {websocket.remote_address} on path '{path}'")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.debug(f"Received message: {data}")

                if "jsonrpc" not in data or data["jsonrpc"] != "2.0":
                    error_response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Invalid Request"},
                        "id": data.get("id")
                    }
                    await websocket.send(json.dumps(error_response))
                    continue

                request_id = data.get("id")
                method = data.get("method")
                params = data.get("params", {})

                response = {"jsonrpc": "2.0", "id": request_id}

                if method == "component.updateInput":
                    component_name = params.get("componentName")
                    inputs = params.get("inputs")
                    if not component_name or not inputs:
                        response["error"] = {"code": -32602, "message": "Invalid params for component.updateInput"}
                    else:
                        try:
                            # Use the provided registry to get the component instance
                            instance = registry.get_component_instance(component_name)
                            if instance:
                                result = await instance.update(inputs)
                                response["result"] = result
                            else:
                                response["error"] = {"code": -32001, "message": f"Component {component_name} not found"}
                        except Exception as e:
                            logger.error(f"Error during component.updateInput: {e}", exc_info=True)
                            response["error"] = {"code": -32000, "message": f"Server error: {str(e)}"}

                elif method == "component.getState":
                    component_name = params.get("componentName")
                    if not component_name:
                        response["error"] = {"code": -32602, "message": "Invalid params for component.getState"}
                    else:
                        try:
                            instance = registry.get_component_instance(component_name)
                            if instance:
                                response["result"] = instance.get_state()
                            else:
                                response["error"] = {"code": -32001, "message": f"Component {component_name} not found"}
                        except Exception as e:
                            logger.error(f"Error during component.getState: {e}", exc_info=True)
                            response["error"] = {"code": -32000, "message": f"Server error: {str(e)}"}

                else:
                    response["error"] = {"code": -32601, "message": "Method not found"}

                await websocket.send(json.dumps(response))
                logger.debug(f"Sent response: {response}")

            except json.JSONDecodeError:
                logger.error("Failed to decode JSON message.")
                error_response = {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
                await websocket.send(json.dumps(error_response))
            except Exception as e:
                logger.error(f"Unhandled error in websocket_handler loop: {e}", exc_info=True)
                # Send a generic error if possible and id is known
                error_id = None
                try: # Try to get id from data if it was parsed
                    error_id = data.get("id") if 'data' in locals() and isinstance(data, dict) else None
                except Exception:
                    pass # Ignore if data is not available or not a dict

                error_response = {"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Internal server error: {str(e)}"}, "id": error_id}
                await websocket.send(json.dumps(error_response))

    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"Client {websocket.remote_address} disconnected normally.")
    except websockets.exceptions.ConnectionClosedError as e:
        logger.warning(f"Client {websocket.remote_address} disconnected with error: {e}")
    except Exception as e:
        logger.error(f"Connection handler for {websocket.remote_address} failed with unexpected error: {e}", exc_info=True)
    finally:
        logger.info(f"Connection with {websocket.remote_address} closed.")


async def setup_and_start_servers():
    # Initialize and register the AIChatInterfaceBackend component
    chat_backend_instance = AIChatInterfaceBackend(component_id="AIChatInterface")
    component_registry.register_component("AIChatInterface", AIChatInterfaceBackend, instance=chat_backend_instance)

    # Use functools.partial to pass the chat_backend and registry to the handler
    # The handler for websockets.serve should only expect the 'websocket' (connection) argument.
    partial_websocket_handler = functools.partial(
        websocket_handler,
        chat_backend=chat_backend_instance, # This will be passed as a keyword argument
        registry=component_registry         # This will also be passed as a keyword argument
    )

    # The process_request hook is called with (websocket, path)
    # It will attach the path to the websocket object for the main handler to use.
    server = await websockets.serve(
        partial_websocket_handler,
        "localhost",
        WS_PORT,
        process_request=process_request_hook # Pass the hook here
    )
    logger.info(f"WebSocket server started on ws://localhost:{WS_PORT}")
    return server

async def main():
    server = await setup_and_start_servers()
    try:
        await server.wait_closed()  # Keep the server running
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    finally:
        server.close()
        await server.wait_closed() # Ensure server is closed before exiting
        logger.info("Server closed.")

if __name__ == "__main__":
    asyncio.run(main())
