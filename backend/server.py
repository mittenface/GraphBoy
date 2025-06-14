import asyncio
import json
import websockets
import logging
import functools
from backend.component_registry import ComponentRegistry
from backend.event_bus import EventBus # Added
from components.AIChatInterface.backend import AIChatInterfaceBackend as ActualAIChatInterfaceBackend

# Configure basic logging
# logging.basicConfig(level=logging.DEBUG) # Moved to main() for better control
logger = logging.getLogger(__name__)

WS_PORT = 8765
event_bus_instance = EventBus() # Added
logger.info(f"Global EventBus instance created: {event_bus_instance}")

# Global registry instance
component_registry_instance = ComponentRegistry(event_bus=event_bus_instance) # Modified, renamed for clarity
logger.info(f"Global ComponentRegistry instance created: {component_registry_instance} with EventBus.")

# class AIChatInterfaceBackend(ComponentInterface): # Commenting out the old local class
#     """
#     A backend component that interacts with a chat model.
#     """
#     def __init__(self, component_id=None):
#         self.component_id = component_id or generate_unique_id()
#         self.state = {"status": "initialized", "history": []}
#         logger.info(f"AIChatInterfaceBackend {self.component_id} initialized.")
#
#     async def update(self, inputs: dict) -> dict:
#         logger.info(f"AIChatInterfaceBackend {self.component_id} update called with inputs: {inputs}")
#         user_input = inputs.get("userInput")
#         # Simulate model processing
#         await asyncio.sleep(0.1) # Simulate async work
#         response_text = f"Mock response to: {user_input}"
#
#         self.state["history"].append({"user": user_input, "assistant": response_text})
#         self.state["status"] = "updated"
#
#         return {
#             "status": "success",
#             "componentId": self.component_id,
#             "responseText": response_text,
#             "updatedState": self.state
#         }
#
#     def get_state(self) -> dict:
#         logger.info(f"AIChatInterfaceBackend {self.component_id} get_state called.")
#         return self.state
#
#     def get_component_id(self) -> str:
#         return self.component_id

# component_registry is now component_registry_instance

# Dictionary to store client WebSocket connections mapping component_id to websocket object
# This might need rethinking if one websocket can interact with multiple components over time.
# For now, we'll associate a websocket with the *first* component_id it interacts with for cleanup.
client_connections: dict[websockets.WebSocketServerProtocol, str] = {} # Store ws -> component_id for cleanup
active_component_sockets: dict[str, websockets.WebSocketServerProtocol] = {} # Store component_id -> ws for sending

async def send_component_output(component_id: str, output_name: str, data: any):
    """
    Sends a component.emitOutput message to the client via WebSocket.
    """
    websocket = active_component_sockets.get(component_id) # Changed to use active_component_sockets
    if websocket:
        message = {
            "jsonrpc": "2.0",
            "method": "component.emitOutput",
            "params": {
                "componentId": component_id,
                "outputName": output_name,
                "data": data
            }
        }
        try:
            await websocket.send(json.dumps(message))
            logger.info(f"Sent component.emitOutput for {component_id}: {output_name}")
        except Exception as e:
            logger.error(f"Error sending component.emitOutput for {component_id}: {e}", exc_info=True)
    else:
        logger.warning(f"No WebSocket connection found for component_id: {component_id} when trying to emit output: {output_name}")

async def process_request_hook(websocket, path_from_hook: str):
    """
    Hook to capture the request path and attach it to the websocket connection object.
    This is called by websockets.serve for each new connection, before the main handler.
    """
    logger.debug(f"process_request_hook: path '{path_from_hook}' attached to connection {websocket.id}")
    websocket.actual_request_path = path_from_hook # Attach the path here

async def websocket_handler(websocket: websockets.WebSocketServerProtocol, registry: ComponentRegistry):
    """
    Handles WebSocket connections and routes JSON-RPC requests.
    """
    path = getattr(websocket, 'actual_request_path', '/')
    logger.info(f"Client connected: {websocket.id} from {websocket.remote_address} on path '{path}'")

    component_id_associated_with_ws: str | None = None

    try:
        async for message_str in websocket:
            data = {} # Ensure data is defined for error logging scope
            try:
                data = json.loads(message_str)
                logger.debug(f"WS {websocket.id} received message: {data}")

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
                current_component_id = params.get("componentName") # Used by most component methods

                if current_component_id:
                    # Associate this websocket with this component_id if not already done
                    if not component_id_associated_with_ws:
                        component_id_associated_with_ws = current_component_id
                        client_connections[websocket] = current_component_id
                        logger.info(f"WS {websocket.id} associated with component_id: {current_component_id}")

                    # Update active socket for this component_id
                    if active_component_sockets.get(current_component_id) != websocket:
                        active_component_sockets[current_component_id] = websocket
                        logger.info(f"Active WebSocket for component_id '{current_component_id}' is now {websocket.id}")

                if method == "component.updateInput":
                    inputs = params.get("inputs")
                    if not current_component_id or inputs is None: # Check for None explicitly if inputs can be empty dict
                        response["error"] = {"code": -32602, "message": "Invalid params for component.updateInput (missing componentName or inputs)"}
                    else:
                        instance = registry.get_component_instance(current_component_id)
                        if instance:
                            try:
                                result = await instance.update(inputs)
                                response["result"] = result
                            except Exception as e:
                                logger.error(f"Error during component.updateInput for {current_component_id}: {e}", exc_info=True)
                                response["error"] = {"code": -32000, "message": f"Server error during update: {str(e)}"}
                        else:
                            response["error"] = {"code": -32001, "message": f"Component '{current_component_id}' not found"}

                elif method == "component.getState":
                    if not current_component_id:
                        response["error"] = {"code": -32602, "message": "Invalid params for component.getState (missing componentName)"}
                    else:
                        instance = registry.get_component_instance(current_component_id)
                        if instance:
                            try:
                                response["result"] = instance.get_state()
                            except Exception as e:
                                logger.error(f"Error during component.getState for {current_component_id}: {e}", exc_info=True)
                                response["error"] = {"code": -32000, "message": f"Server error during getState: {str(e)}"}
                        else:
                            response["error"] = {"code": -32001, "message": f"Component '{current_component_id}' not found"}
                else:
                    response["error"] = {"code": -32601, "message": f"Method '{method}' not found"}

                await websocket.send(json.dumps(response))
                logger.debug(f"WS {websocket.id} sent response: {response}")

            except json.JSONDecodeError:
                logger.error(f"WS {websocket.id} failed to decode JSON message: {message_str}", exc_info=True)
                error_response = {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
                await websocket.send(json.dumps(error_response))
            except Exception as e:
                logger.error(f"WS {websocket.id} unhandled error in message processing loop: {e}", exc_info=True)
                error_id = data.get("id") if isinstance(data, dict) else None
                error_response = {"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Internal server error: {str(e)}"}, "id": error_id}
                try:
                    await websocket.send(json.dumps(error_response))
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"WS {websocket.id} connection closed while trying to send error response.")
                    break # Exit message loop if connection is closed

    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"WS {websocket.id} client disconnected normally from {websocket.remote_address}.")
    except websockets.exceptions.ConnectionClosedError as e:
        logger.warning(f"WS {websocket.id} client disconnected with error from {websocket.remote_address}: {e}")
    except Exception as e:
        logger.error(f"WS {websocket.id} connection handler failed with unexpected error: {e}", exc_info=True)
    finally:
        logger.info(f"WS {websocket.id} connection with {websocket.remote_address} closing.")
        # Clean up connections
        if websocket in client_connections:
            associated_cid = client_connections.pop(websocket)
            logger.info(f"Removed primary association for WS {websocket.id} with component_id: {associated_cid}")
            # Also remove from active_component_sockets if this was the active socket for that component
            if active_component_sockets.get(associated_cid) == websocket:
                active_component_sockets.pop(associated_cid)
                logger.info(f"Removed WS {websocket.id} as active socket for component_id: {associated_cid}")

        # Fallback: Iterate through active_component_sockets to find and remove this websocket instance if it's still listed anywhere
        # This handles cases where client_connections might not have been set but active_component_sockets was.
        extra_cids_to_clear = [cid for cid, ws in active_component_sockets.items() if ws == websocket]
        for cid_to_clear in extra_cids_to_clear:
            active_component_sockets.pop(cid_to_clear)
            logger.info(f"Cleared WS {websocket.id} from active_component_sockets for component_id: {cid_to_clear} during final cleanup.")


async def setup_and_start_servers():
    logger.info("Setting up and starting servers...")
    component_id = "AIChatInterface"

    # Instantiate the actual backend component, now also passing the event_bus
    chat_backend_instance = ActualAIChatInterfaceBackend(
        component_id=component_id,
        send_component_output_func=send_component_output,
        event_bus=event_bus_instance # Added event_bus
    )
    logger.info(f"Instantiated {component_id} backend: {chat_backend_instance} with EventBus.")

    # Register the component instance with the global registry
    component_registry_instance.register_component(
        name=component_id,
        component_class=ActualAIChatInterfaceBackend, # Pass the class for potential type checking or metadata
        instance=chat_backend_instance
    )
    logger.info(f"Registered {component_id} with ComponentRegistry.")

    # Use functools.partial to pass the registry to the websocket handler
    partial_websocket_handler = functools.partial(
        websocket_handler,
        registry=component_registry_instance # Use the renamed instance
    )

    # The process_request hook is called with (websocket, path) by websockets.serve
    # It will attach the path to the websocket object for the main handler to use.
    server = await websockets.serve(
        partial_websocket_handler,
        "localhost",
        WS_PORT,
        process_request=process_request_hook # Pass the hook here
    )
    logger.info(f"WebSocket server starting on ws://localhost:{WS_PORT}...")
    return server

async def main():
    # Configure basic logging (moved here from global scope)
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Application starting...")

    # Discover components from a directory (example)
    # component_registry_instance.discover_components("components") # If you have such a directory
    # For now, we are manually registering AIChatInterface

    server = await setup_and_start_servers()
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logger.info("Server shutting down due to KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Server shutdown due to unexpected error: {e}", exc_info=True)
    finally:
        if server:
            server.close()
            await server.wait_closed()
        logger.info("Server closed.")

if __name__ == "__main__":
    asyncio.run(main())
