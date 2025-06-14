import asyncio
import json
import websockets
import logging
import functools
from backend.component_registry import ComponentRegistry
from backend.event_bus import EventBus  # Added
from components.AIChatInterface.backend import AIChatInterfaceBackend as ActualAIChatInterfaceBackend

# Configure basic logging
# logging.basicConfig(level=logging.DEBUG)  # Moved to main() for better control
logger = logging.getLogger(__name__)

WS_PORT = 8765

event_bus_instance = EventBus()  # Added
logger.info(f"Global EventBus instance created: {event_bus_instance}")

# Global registry instance
# Modified, renamed for clarity
component_registry_instance = ComponentRegistry(event_bus=event_bus_instance)
logger.info(
    f"Global ComponentRegistry instance created: {component_registry_instance} "
    f"with EventBus."
)

# Dictionary to store client WebSocket connections mapping component_id to
# websocket object
# Store ws -> component_id for cleanup
client_connections: dict[websockets.WebSocketServerProtocol, str] = {}
# Store component_id -> ws for sending
active_component_sockets: dict[str, websockets.WebSocketServerProtocol] = {}

# Dictionary to store active connections between components
active_connections: dict[str, dict] = {}

# Return type changed, returns None if only publishing
def send_component_output(component_id: str, output_name: str, data: any) -> None:
    """
    Sends a component.emitOutput message to the client via WebSocket
    and publishes an event to the event bus for inter-component communication.
    """
    # Publish event to EventBus for inter-component communication
    event_name = _get_event_name(component_id, output_name)
    logger.info(f"Publishing event: {event_name} with data: {data}")
    # Fire-and-forget
    asyncio.create_task(event_bus_instance.publish(event_name, data=data))

    # Send message to WebSocket client (original functionality)
    websocket = active_component_sockets.get(component_id)
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
        # Create a task for sending the WebSocket message, but don't return it directly
        # if the function's primary purpose is now broader.
        asyncio.create_task(_send_message(websocket, message))
        # If the caller specifically needs to await WebSocket send, this design might need adjustment,
        # but for now, we assume fire-and-forget for both.
    else:
        logger.warning(
            f"No WebSocket connection found for component_id: {component_id} "
            f"when trying to emit output via WebSocket: {output_name}"
        )
    # This function no longer exclusively returns the WebSocket send task.
    # Consider if callers relied on this return value. For now, returning None.

async def _send_message(websocket, message: dict):
    try:
        await websocket.send(json.dumps(message))
        logger.info(
            f"Sent component.emitOutput for {message['params']['componentId']}: "
            f"{message['params']['outputName']}"
        )
    except Exception as e:
        logger.error(
            f"Error sending component.emitOutput for "
            f"{message['params']['componentId']}: {e}", exc_info=True
        )

async def process_request_hook(websocket, request_param): # Renamed to request_param
    """
    Hook to capture the request path and attach it to the websocket connection object.
    This is called by websockets.serve for each new connection,
    before the main handler.
    Ensures websocket.actual_request_path is set to a string path.
    """
    path_to_set: str
    logger.debug(
        f"process_request_hook: received request_param: '{request_param}' "
        f"(type: {type(request_param)}) for connection {getattr(websocket, 'id', 'unknown')}"
    )

    # The websockets documentation for process_request states the second arg is
    # `path: str`. However, logs from previous runs indicated that
    # `request_param` might be a Request object.
    # Let's robustly extract the path string.

    # Try to import the specific Request type for isinstance check if possible,
    # otherwise rely on duck typing.
    RequestObjectType = None
    try:
        # Attempt to import the specific type if available and known.
        # Based on logs, it was websockets.http11.Request.
        # Note: direct import might fail if library structure changes or is not
        # as expected.
        from websockets.http11 import Request as HTTP11RequestType
        RequestObjectType = HTTP11RequestType
        logger.debug(
            "process_request_hook: Successfully imported "
            "websockets.http11.Request as HTTP11RequestType."
        )
    except ImportError:
        logger.warning(
            "process_request_hook: Could not import websockets.http11.Request. "
            "Will rely on duck typing for path extraction."
        )

    if isinstance(request_param, str):
        path_to_set = request_param
        logger.debug(
            "process_request_hook: request_param is a string. "
            "Setting actual_request_path directly to '%s'.",
            path_to_set
        )
    elif (RequestObjectType and
          isinstance(request_param, RequestObjectType) and
          hasattr(request_param, 'path')):
        path_to_set = request_param.path
        logger.warning(
            f"process_request_hook: request_param is a known Request object "
            f"(type: {type(request_param)}). Used its .path attribute: '{path_to_set}'."
        )
    # Duck typing for other Request-like objects
    elif (hasattr(request_param, 'path') and
          isinstance(getattr(request_param, 'path', None), str)):
        path_to_set = getattr(request_param, 'path')
        logger.warning(
            f"process_request_hook: request_param (type: {type(request_param)}) "
            f"is not a string but has a .path string attribute. "
            f"Used .path: '{path_to_set}'."
        )
    else:
        logger.error(
            f"process_request_hook: request_param is of unexpected type "
            f"({type(request_param)}) and does not have a .path string attribute. "
            f"Defaulting path to '/'. Value: {request_param}"
        )
        path_to_set = "/"

    websocket.actual_request_path = path_to_set
    logger.info(
        f"process_request_hook: websocket.actual_request_path finally set to "
        f"'{websocket.actual_request_path}' (type: {type(websocket.actual_request_path)})"
    )

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
        return {"error": {"code": -32602,
                          "message": "Invalid params: connectionId is required"}}

    logger.info(
        f"Attempting to create connection: {connection_id} from "
        f"{source_component_id}:{source_port_name} to "
        f"{target_component_id}:{target_port_name}"
    )

    # Validate parameters
    if not all([connection_id, source_component_id, source_port_name,
                target_component_id, target_port_name]):
        logger.error(
            "connection.create failed: Missing one or more required parameters."
        )
        return {"error": {"code": -32602,
                          "message": "Invalid params: Missing required parameters"}}

    # Fetch port details
    source_port_details = component_registry_instance.get_port_details(
        source_component_id, source_port_name
    )
    target_port_details = component_registry_instance.get_port_details(
        target_component_id, target_port_name
    )

    if not source_port_details:
        logger.error(
            f"connection.create failed: Source port details not found for "
            f"{source_component_id}:{source_port_name}"
        )
        return {"error": {"code": -32004,
                          "message": f"Port details not found for source port "
                                     f"{source_component_id}:{source_port_name}."}}
    if not target_port_details:
        logger.error(
            f"connection.create failed: Target port details not found for "
            f"{target_component_id}:{target_port_name}"
        )
        return {"error": {"code": -32004,
                          "message": f"Port details not found for target port "
                                     f"{target_component_id}:{target_port_name}."}}

    # Validate port types
    if source_port_details.get("type") != "output":
        logger.error(
            f"connection.create failed: Source port "
            f"{source_component_id}:{source_port_name} is not an output port."
        )
        return {"error": {"code": -32003,
                          "message": "Invalid connection: Source port must be an output port."}}
    if target_port_details.get("type") != "input":
        logger.error(
            f"connection.create failed: Target port "
            f"{target_component_id}:{target_port_name} is not an input port."
        )
        return {"error": {"code": -32003,
                          "message": "Invalid connection: Target port must be an input port."}}

    # Validate data types
    if source_port_details.get("data_type") != target_port_details.get("data_type"):
        logger.error(
            f"connection.create failed: Data type mismatch between "
            f"{source_component_id}:{source_port_name} "
            f"({source_port_details.get('data_type')}) and "
            f"{target_component_id}:{target_port_name} "
            f"({target_port_details.get('data_type')})."
        )
        return {"error": {"code": -32003,
                          "message": f"Invalid connection: Data type mismatch. "
                                     f"Source is '{source_port_details.get('data_type')}', "
                                     f"Target is '{target_port_details.get('data_type')}'."}}

    # Check target instance (already part of original logic, kept for clarity
    # though redundant if port lookups succeed)
    target_instance = component_registry_instance.get_component_instance(
        target_component_id
    )
    # This check might be redundant if get_port_details implies component existence.
    if not target_instance:
        logger.error(
            f"connection.create failed: Target component '{target_component_id}' "
            f"not found (post port validation)."
        )
        return {"error": {"code": -32001,
                          "message": f"Target component '{target_component_id}' not found."}}

    event_name = _get_event_name(source_component_id, source_port_name)

    async def on_data_received(data: any):
        logger.info(
            f"Connection {connection_id}: Data received on event '{event_name}' "
            f"for {target_component_id}:{target_port_name}"
        )
        try:
            # Retrieve target instance again, or ensure it's properly closed over.
            # For simplicity, retrieving again if necessary,
            # though closure should work.
            current_target_instance = component_registry_instance.get_component_instance(
                target_component_id
            )
            if not current_target_instance:
                logger.error(
                    f"Data received for connection {connection_id}, but target "
                    f"component '{target_component_id}' no longer found."
                )
                return

            if hasattr(current_target_instance, 'process_input'):
                await current_target_instance.process_input(target_port_name, data)
                logger.debug(
                    f"Data processed by {target_component_id} via input port "
                    f"{target_port_name}"
                )
            else:
                logger.error(
                    f"Target component '{target_component_id}' does not have "
                    f"a process_input method."
                )
        except Exception as e:
            logger.error(
                f"Error processing data for connection {connection_id} "
                f"by {target_component_id}: {e}", exc_info=True
            )

    try:
        # subscribe is not an async method
        event_bus_instance.subscribe(event_name, on_data_received)
        logger.info(
            f"Successfully subscribed to event '{event_name}' "
            f"for connection {connection_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to subscribe to event '{event_name}' "
            f"for connection {connection_id}: {e}", exc_info=True
        )
        return {"error": {"code": -32002,
                          "message": f"Failed to subscribe to event: {e}"}}

    details = {
        "connectionId": connection_id,
        "sourceComponentId": source_component_id,
        "sourcePortName": source_port_name,
        "targetComponentId": target_component_id,
        "targetPortName": target_port_name,
        "status": "active",
        "event_name": event_name,
        "callback": on_data_received  # Store the actual callback
    }
    active_connections[connection_id] = details
    logger.info(f"Connection {connection_id} created and stored: {details}")
    return {"status": "success",
            "message": "Connection created successfully",
            "connectionId": connection_id}

def _get_event_name(source_component_id: str, source_port_name: str) -> str:
    """Helper function to define the event naming convention."""
    return f"component_output::{source_component_id}::{source_port_name}"

async def handle_connection_delete(params: dict) -> dict:
    """
    Handles the deletion of an existing connection.
    """
    connection_id = params.get("connectionId")

    if not connection_id:
        logger.error("connection.delete failed: connectionId is required")
        return {"error": {"code": -32602,
                          "message": "Invalid params: connectionId is required"}}

    logger.info(f"Attempting to delete connection: {connection_id}")

    connection_details = active_connections.get(connection_id)
    if connection_details:
        event_name = connection_details.get("event_name")
        callback = connection_details.get("callback")

        if event_name and callback:
            try:
                # unsubscribe is not an async method
                event_bus_instance.unsubscribe(event_name, callback)
                logger.info(
                    f"Successfully unsubscribed from event '{event_name}' "
                    f"for connection {connection_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error unsubscribing from event '{event_name}' "
                    f"for connection {connection_id}: {e}", exc_info=True
                )
                # Optionally, still proceed to delete the connection from
                # active_connections or handle error differently

        del active_connections[connection_id]
        logger.info(f"Connection {connection_id} deleted successfully.")
        return {"status": "success",
                "message": "Connection deleted successfully",
                "connectionId": connection_id}
    else:
        logger.warning(f"Connection {connection_id} not found for deletion.")
        return {"status": "not_found",
                "message": "Connection not found",
                "connectionId": connection_id}

async def websocket_handler(
    websocket: websockets.WebSocketServerProtocol,
    registry: ComponentRegistry
):
    """
    Handles WebSocket connections and routes JSON-RPC requests.
    """
    logger.debug(
        f"websocket_handler: Entered for websocket id {getattr(websocket, 'id', 'unknown')}"
    )

    # process_request_hook is now responsible for ensuring actual_request_path
    # is a string.
    path_to_use = getattr(websocket, 'actual_request_path', '/')

    # Log what we got. It should be a string.
    logger.debug(
        f"websocket_handler: Retrieved websocket.actual_request_path: "
        f"'{path_to_use}' (type: {type(path_to_use)})"
    )

    if not isinstance(path_to_use, str):
        # This case should ideally not be reached if process_request_hook is
        # effective.
        logger.error(
            f"websocket_handler: CRITICAL - path_to_use from "
            f"actual_request_path is NOT a string (type: {type(path_to_use)}). "
            f"Defaulting to '/'. This indicates an issue in process_request_hook."
        )
        path_to_use = '/'

    logger.info(
        f"Client connected: {getattr(websocket, 'id', 'unknown')} from "
        f"{websocket.remote_address} on effective path '{path_to_use}'"
    )

    associated: str | None = None
    ws_id = getattr(websocket, 'id', 'unknown') # For consistent logging

    try:
        # Associate websocket with component ID as early as possible if path
        # indicates it
        if path_to_use and path_to_use.startswith("/ws/component/"):
            potential_cid = path_to_use.split("/ws/component/", 1)[1]
            if potential_cid:
                associated = potential_cid
                client_connections[websocket] = associated
                active_component_sockets[associated] = websocket
                logger.info(
                    f"WS {ws_id}: Associated early with component via path: {associated}"
                )

        # Main message processing loop
        async for message_str in websocket:
            # Define data here to have it in scope for broader exception handling
            # if needed
            data = {}
            try:
                data = json.loads(message_str)
                logger.debug(f"WS {ws_id}: Received message: {data}")

                if data.get("jsonrpc") != "2.0":
                    logger.warning(
                        f"WS {ws_id}: Invalid JSON-RPC version. Message: {message_str}"
                    )
                    await websocket.send(json.dumps({
                        "jsonrpc": "2.0",
                        "error": {"code": -32600,
                                  "message": "Invalid Request: JSON-RPC version must be 2.0"},
                        "id": data.get("id")
                    }))
                    continue

                req_id = data.get("id")
                method = data.get("method")
                params = data.get("params", {})
                resp = {"jsonrpc": "2.0", "id": req_id}

                if not method:
                    logger.warning(
                        f"WS {ws_id}: Missing 'method' in JSON-RPC request. Data: {data}"
                    )
                    if req_id is not None:
                         resp["error"] = {"code": -32600,
                                          "message": "Invalid Request: 'method' is required"}
                         await websocket.send(json.dumps(resp))
                    continue

                cid_from_params = params.get("componentName") or params.get("componentId")
                if cid_from_params and not associated:
                    associated = cid_from_params
                    if websocket not in client_connections:
                         client_connections[websocket] = associated
                         active_component_sockets[associated] = websocket
                         logger.info(
                             f"WS {ws_id}: Associated with component via message: {associated}"
                            )
                    elif client_connections[websocket] != associated:
                         logger.warning(
                             f"WS {ws_id}: Tried to re-associate from "
                             f"{client_connections[websocket]} to {associated}. Denied."
                            )

                target_component_id_for_method = associated
                if method not in ["connection.create", "connection.delete"]:
                    if not target_component_id_for_method and cid_from_params:
                        target_component_id_for_method = cid_from_params

                    # Only check for component existence if a component is targeted
                    # and the method is not a global discovery method.
                    if target_component_id_for_method and \
                       not registry.get_component_instance(target_component_id_for_method) and \
                       method not in ["component.discover"]:
                        logger.error(
                            f"WS {ws_id}: Method '{method}' targeted component "
                            f"'{target_component_id_for_method}' which was not "
                            f"found."
                        )
                        if req_id is not None:
                            resp["error"] = {"code": -32001,
                                             "message": f"Component '{target_component_id_for_method}' not found."}
                            await websocket.send(json.dumps(resp))
                        continue

                # Method routing logic
                if method == "component.updateInput":
                    inputs = params.get("inputs")
                    current_cid_for_op = cid_from_params or associated
                    if not current_cid_for_op or inputs is None:
                        resp["error"] = {"code": -32602,
                                         "message": "Invalid params for component.updateInput: componentName/Id and inputs required"}
                    else:
                        inst = registry.get_component_instance(current_cid_for_op)
                        if inst: resp["result"] = await inst.update(inputs)
                        else: resp["error"] = {"code": -32001,
                                               "message": f"Component instance '{current_cid_for_op}' not found for updateInput"}
                elif method == "component.getState":
                    current_cid_for_op = cid_from_params or associated
                    if not current_cid_for_op:
                        resp["error"] = {"code": -32602,
                                         "message": "Missing componentName for getState"}
                    else:
                        inst = registry.get_component_instance(current_cid_for_op)
                        if inst: resp["result"] = inst.get_state()
                        else: resp["error"] = {"code": -32001,
                                               "message": f"Component '{current_cid_for_op}' not found for getState"}
                elif method == "connection.create":
                    result = await handle_connection_create(params)
                    if "error" in result: resp["error"] = result["error"]
                    else: resp["result"] = result
                elif method == "connection.delete":
                    result = await handle_connection_delete(params)
                    if "error" in result: resp["error"] = result["error"]
                    else: resp["result"] = result
                else:
                    resp["error"] = {"code": -32601,
                                     "message": f"Method '{method}' not found"}

                if req_id is not None:
                    await websocket.send(json.dumps(resp))
                    logger.debug(
                        f"WS {ws_id}: Sent response for req_id {req_id}: {resp}"
                    )
                else:
                    logger.debug(
                        f"WS {ws_id}: Notification '{method}' received. No response sent."
                    )

            except json.JSONDecodeError:
                logger.error(
                    f"WS {ws_id}: JSON Parse error: {message_str[:200]}...",
                    exc_info=True
                )
                if websocket.open:
                    await websocket.send(json.dumps({
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None
                    }))
                break # Stop processing messages for this connection on parse error
            # Catches ConnectionClosedOK and ConnectionClosedError
            except websockets.exceptions.ConnectionClosed:
                logger.warning(
                    f"WS {ws_id}: Connection closed while processing message or "
                    f"sending response.", exc_info=True
                )
                break
            except Exception as e: # Catch-all for other errors during message processing
                logger.error(f"WS {ws_id}: Error processing message: {e}", exc_info=True)
                error_id_for_response = data.get("id") if isinstance(data, dict) and data else None
                if error_id_for_response is not None and websocket.open:
                    try:
                        await websocket.send(json.dumps({
                            "jsonrpc": "2.0",
                            "error": {"code": -32000, "message": f"Internal error: {str(e)}"},
                            "id": error_id_for_response
                        }))
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning(
                            f"WS {ws_id}: Tried to send processing error, but "
                            f"connection already closed.", exc_info=True
                        )
                # Decide if to break or continue based on error. For most errors,
                # continuing might be risky.
                # For now, let's break to ensure finally is reached.
                break

    # Explicitly catch connection closed exceptions outside the loop to ensure logging
    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"WS {ws_id}: Connection closed cleanly (OK).")
    except websockets.exceptions.ConnectionClosedError as e:
        logger.warning(f"WS {ws_id}: Connection closed with error: {e}", exc_info=True)
    # Catch-all for errors in websocket_handler's setup or unexpected issues
    except Exception as e:
        logger.error(f"WS {ws_id}: Handler failed unexpectedly: {e}", exc_info=True)
    finally:
        logger.info(
            f"WS {ws_id}: Entering finally block for cleanup. "
            f"Associated ID: {associated}"
        )
        if associated and active_component_sockets.get(associated) == websocket:
            active_component_sockets.pop(associated, None)
            logger.info(
                f"WS {ws_id}: Cleaned up active_component_socket for component: {associated}"
            )

        if client_connections.pop(websocket, None):
            logger.info(f"WS {ws_id}: Cleaned up client_connection for websocket.")
        else:
            logger.debug(
                f"WS {ws_id}: Websocket not found in client_connections during cleanup."
            )
        logger.info(f"WS {ws_id}: Finished cleanup.")

async def setup_and_start_servers():
    component_id = "AIChatInterface"
    inst = ActualAIChatInterfaceBackend(
        component_id=component_id,
        send_component_output_func=send_component_output,
        event_bus=event_bus_instance
    )
    component_registry_instance.register_component(
        name=component_id,
        component_class=ActualAIChatInterfaceBackend,
        instance=inst
    )
    handler = functools.partial(websocket_handler,
                                registry=component_registry_instance)
    server = await websockets.serve(
        handler, "localhost", WS_PORT,
        process_request=process_request_hook
    )
    logger.info(
        f"WebSocket server running on ws://localhost:{WS_PORT} "
        f"(within setup_and_start_servers)"
    )
    # await server.wait_closed() # Removed: This would block until server stops
    return server

async def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # setup_and_start_servers now blocks until server is closed.
    await setup_and_start_servers()
    logger.info("WebSocket server has shut down.")


if __name__ == "__main__":
    asyncio.run(main())