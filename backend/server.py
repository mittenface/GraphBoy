import asyncio
import json
import websockets
import logging
import functools
from backend.component_registry import ComponentRegistry # ComponentInterface might not be needed here anymore
# from backend.utils import generate_unique_id # May not be needed if component_id is hardcoded or passed
from components.AIChatInterface.backend import AIChatInterfaceBackend as ActualAIChatInterfaceBackend # Renamed to avoid conflict

# Configure basic logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

WS_PORT = 8765

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

# Global registry instance (assuming ComponentRegistry is thread-safe or managed appropriately)
component_registry = ComponentRegistry()
# Make sure ComponentInterface is imported if base class is needed by registry or other components
# For now, ActualAIChatInterfaceBackend does not explicitly inherit ComponentInterface.
# This might need adjustment if ComponentRegistry expects ComponentInterface instances.
# For this task, we assume ComponentRegistry can handle objects that implement the required methods (duck typing).

# Dictionary to store client WebSocket connections mapping component_id to websocket object
client_connections = {}

# Dictionary to store active connections between components
active_connections = {}

async def send_component_output(component_id: str, output_name: str, data: any):
    """
    Sends a component.emitOutput message to the client via WebSocket.
    """
    websocket = client_connections.get(component_id)
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

async def handle_connection_create(params: dict) -> dict:
    """
    Handles the creation of a new connection between component ports.
    """
    connection_id = params.get("connectionId")
    source_component_id = params.get("sourceComponentId")
    source_port_name = params.get("sourcePortName")
    target_component_id = params.get("targetComponentId")
    target_port_name = params.get("targetPortName")

    if not connection_id:
        logger.error("connection.create failed: connectionId is required")
        return {"error": {"code": -32602, "message": "Invalid params: connectionId is required"}}

    logger.info(f"Attempting to create connection: {connection_id} from {source_component_id}:{source_port_name} to {target_component_id}:{target_port_name}")

    connection_details = {
        "connectionId": connection_id,
        "sourceComponentId": source_component_id,
        "sourcePortName": source_port_name,
        "targetComponentId": target_component_id,
        "targetPortName": target_port_name,
        "status": "active" # Or any other relevant status
    }
    active_connections[connection_id] = connection_details
    logger.info(f"Connection {connection_id} created successfully.")
    return {"status": "success", "message": "Connection created successfully", "connectionId": connection_id}

async def handle_connection_delete(params: dict) -> dict:
    """
    Handles the deletion of an existing connection.
    """
    connection_id = params.get("connectionId")

    if not connection_id:
        logger.error("connection.delete failed: connectionId is required")
        return {"error": {"code": -32602, "message": "Invalid params: connectionId is required"}}

    logger.info(f"Attempting to delete connection: {connection_id}")

    if connection_id in active_connections:
        del active_connections[connection_id]
        logger.info(f"Connection {connection_id} deleted successfully.")
        return {"status": "success", "message": "Connection deleted successfully", "connectionId": connection_id}
    else:
        logger.warning(f"Connection {connection_id} not found for deletion.")
        return {"status": "not_found", "message": "Connection not found", "connectionId": connection_id}

async def websocket_handler(websocket, registry: ComponentRegistry): # chat_backend argument removed, registry will provide the instance
    """
    Handles WebSocket connections and routes JSON-RPC requests.
    The 'path' argument is no longer directly here, it's accessed via websocket.actual_request_path.
    """
    path = getattr(websocket, 'actual_request_path', '/') # Get path from the connection object
    logger.info(f"Client connected from {websocket.remote_address} on path '{path}'")

    # The component_id might not be known on initial connection,
    # It will be associated when the first component-specific message arrives.

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

                # Component identifier, typically 'componentName' from client params
                component_id_from_request = None

                if method == "component.updateInput":
                    component_id_from_request = params.get("componentName")
                    inputs = params.get("inputs")
                    if not component_id_from_request or not inputs:
                        response["error"] = {"code": -32602, "message": "Invalid params for component.updateInput"}
                    else:
                        # Store connection before processing
                        if component_id_from_request not in client_connections:
                            client_connections[component_id_from_request] = websocket
                            logger.info(f"WebSocket connection stored for component_id: {component_id_from_request}")
                        elif client_connections[component_id_from_request] != websocket:
                            # This might happen if a component ID is reused or if client reconnects
                            client_connections[component_id_from_request] = websocket
                            logger.info(f"WebSocket connection updated for component_id: {component_id_from_request}")

                        try:
                            # Use the provided registry to get the component instance
                            instance = registry.get_component_instance(component_id_from_request)
                            if instance:
                                result = await instance.update(inputs)
                                response["result"] = result
                            else:
                                response["error"] = {"code": -32001, "message": f"Component {component_id_from_request} not found"}
                        except Exception as e:
                            logger.error(f"Error during component.updateInput: {e}", exc_info=True)
                            response["error"] = {"code": -32000, "message": f"Server error: {str(e)}"}

                elif method == "component.getState":
                    component_id_from_request = params.get("componentName")
                    if not component_id_from_request:
                        response["error"] = {"code": -32602, "message": "Invalid params for component.getState"}
                    else:
                        # Store connection before processing
                        if component_id_from_request not in client_connections:
                            client_connections[component_id_from_request] = websocket
                            logger.info(f"WebSocket connection stored for component_id: {component_id_from_request}")
                        elif client_connections[component_id_from_request] != websocket:
                            client_connections[component_id_from_request] = websocket
                            logger.info(f"WebSocket connection updated for component_id: {component_id_from_request}")

                        try:
                            instance = registry.get_component_instance(component_id_from_request)
                            if instance:
                                response["result"] = instance.get_state()
                            else:
                                response["error"] = {"code": -32001, "message": f"Component {component_id_from_request} not found"}
                        except Exception as e:
                            logger.error(f"Error during component.getState: {e}", exc_info=True)
                            response["error"] = {"code": -32000, "message": f"Server error: {str(e)}"}

                elif method == "connection.create":
                    logger.info(f"Received connection.create request with params: {params}")
                    response_data = await handle_connection_create(params)
                    if "error" in response_data:
                        response["error"] = response_data["error"]
                    else:
                        response["result"] = response_data

                elif method == "connection.delete":
                    logger.info(f"Received connection.delete request with params: {params}")
                    response_data = await handle_connection_delete(params)
                    if "error" in response_data:
                        response["error"] = response_data["error"]
                    else:
                        response["result"] = response_data

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
        # Clean up client_connections for this websocket
        # This is important if a client disconnects and the component_id might be reused later
        # or to prevent sending messages to a closed connection.
        component_ids_to_remove = [cid for cid, ws in client_connections.items() if ws == websocket]
        for cid in component_ids_to_remove:
            del client_connections[cid]
            logger.info(f"Removed WebSocket connection for component_id: {cid} due to disconnection.")


async def setup_and_start_servers():
    # Initialize and register the AIChatInterfaceBackend component
    # Crucially, we now instantiate ActualAIChatInterfaceBackend from components directory
    # and pass the send_component_output function to it.
    component_id = "AIChatInterface"
    chat_backend_instance = ActualAIChatInterfaceBackend(
        component_id=component_id,
        send_component_output_func=send_component_output  # Pass the actual async function
    )
    # The class itself is ActualAIChatInterfaceBackend, not the old local one
    component_registry.register_component(component_id, ActualAIChatInterfaceBackend, instance=chat_backend_instance)

    # Use functools.partial to pass the registry to the handler
    # The handler for websockets.serve should only expect the 'websocket' (connection) argument.
    # chat_backend is no longer passed directly as it's obtained via registry
    partial_websocket_handler = functools.partial(
        websocket_handler,
        registry=component_registry
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
