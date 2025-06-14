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
component_registry_instance = ComponentRegistry(event_bus=event_bus_instance)  # Modified, renamed for clarity
logger.info(f"Global ComponentRegistry instance created: {component_registry_instance} with EventBus.")

# Dictionary to store client WebSocket connections mapping component_id to websocket object
client_connections: dict[websockets.WebSocketServerProtocol, str] = {}  # Store ws -> component_id for cleanup
active_component_sockets: dict[str, websockets.WebSocketServerProtocol] = {}  # Store component_id -> ws for sending

# Dictionary to store active connections between components
active_connections: dict[str, dict] = {}

def send_component_output(component_id: str, output_name: str, data: any) -> None: # Return type changed, returns None if only publishing
    """
    Sends a component.emitOutput message to the client via WebSocket
    and publishes an event to the event bus for inter-component communication.
    """
    # Publish event to EventBus for inter-component communication
    event_name = _get_event_name(component_id, output_name)
    logger.info(f"Publishing event: {event_name} with data: {data}")
    asyncio.create_task(event_bus_instance.publish(event_name, data=data)) # Fire-and-forget

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
        logger.warning(f"No WebSocket connection found for component_id: {component_id} when trying to emit output via WebSocket: {output_name}")
    # This function no longer exclusively returns the WebSocket send task.
    # Consider if callers relied on this return value. For now, returning None.

async def _send_message(websocket, message: dict):
    try:
        await websocket.send(json.dumps(message))
        logger.info(f"Sent component.emitOutput for {message['params']['componentId']}: {message['params']['outputName']}")
    except Exception as e:
        logger.error(f"Error sending component.emitOutput for {message['params']['componentId']}: {e}", exc_info=True)

async def process_request_hook(websocket, path: str):
    """
    Hook to capture the request path and attach it to the websocket connection object.
    This is called by websockets.serve for each new connection, before the main handler.
    """
    logger.debug(f"process_request_hook: path '{path}' attached to connection {getattr(websocket, 'id', 'unknown')}")
    websocket.actual_request_path = path

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

    # Validate parameters
    if not all([connection_id, source_component_id, source_port_name, target_component_id, target_port_name]):
        logger.error("connection.create failed: Missing one or more required parameters.")
        return {"error": {"code": -32602, "message": "Invalid params: Missing required parameters"}}

    target_instance = component_registry_instance.get_component_instance(target_component_id)
    if not target_instance:
        logger.error(f"connection.create failed: Target component '{target_component_id}' not found.")
        return {"error": {"code": -32001, "message": f"Target component '{target_component_id}' not found"}}

    event_name = _get_event_name(source_component_id, source_port_name)

    async def on_data_received(data: any):
        logger.info(f"Connection {connection_id}: Data received on event '{event_name}' for {target_component_id}:{target_port_name}")
        try:
            # Retrieve target instance again, or ensure it's properly closed over.
            # For simplicity, retrieving again if necessary, though closure should work.
            current_target_instance = component_registry_instance.get_component_instance(target_component_id)
            if not current_target_instance:
                logger.error(f"Data received for connection {connection_id}, but target component '{target_component_id}' no longer found.")
                return

            if hasattr(current_target_instance, 'process_input'):
                await current_target_instance.process_input(target_port_name, data)
                logger.debug(f"Data processed by {target_component_id} via input port {target_port_name}")
            else:
                logger.error(f"Target component '{target_component_id}' does not have a process_input method.")
        except Exception as e:
            logger.error(f"Error processing data for connection {connection_id} by {target_component_id}: {e}", exc_info=True)

    try:
        await event_bus_instance.subscribe(event_name, on_data_received)
        logger.info(f"Successfully subscribed to event '{event_name}' for connection {connection_id}")
    except Exception as e:
        logger.error(f"Failed to subscribe to event '{event_name}' for connection {connection_id}: {e}", exc_info=True)
        return {"error": {"code": -32002, "message": f"Failed to subscribe to event: {e}"}}

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
    return {"status": "success", "message": "Connection created successfully", "connectionId": connection_id}

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
        return {"error": {"code": -32602, "message": "Invalid params: connectionId is required"}}

    logger.info(f"Attempting to delete connection: {connection_id}")

    connection_details = active_connections.get(connection_id)
    if connection_details:
        event_name = connection_details.get("event_name")
        callback = connection_details.get("callback")

        if event_name and callback:
            try:
                await event_bus_instance.unsubscribe(event_name, callback)
                logger.info(f"Successfully unsubscribed from event '{event_name}' for connection {connection_id}")
            except Exception as e:
                logger.error(f"Error unsubscribing from event '{event_name}' for connection {connection_id}: {e}", exc_info=True)
                # Optionally, still proceed to delete the connection from active_connections or handle error differently

        del active_connections[connection_id]
        logger.info(f"Connection {connection_id} deleted successfully.")
        return {"status": "success", "message": "Connection deleted successfully", "connectionId": connection_id}
    else:
        logger.warning(f"Connection {connection_id} not found for deletion.")
        return {"status": "not_found", "message": "Connection not found", "connectionId": connection_id}

async def websocket_handler(
    websocket: websockets.WebSocketServerProtocol,
    registry: ComponentRegistry
):
    """
    Handles WebSocket connections and routes JSON-RPC requests.
    """
    path = getattr(websocket, 'actual_request_path', '/')
    logger.info(f"Client connected: {getattr(websocket, 'id', 'unknown')} from {websocket.remote_address} on path '{path}'")

    associated: str | None = None
    try:
        async for message_str in websocket:
            data = {}
            try:
                data = json.loads(message_str)
                logger.debug(f"WS received message: {data}")

                # JSON-RPC 2.0 validation
                if data.get("jsonrpc") != "2.0":
                    await websocket.send(json.dumps({
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Invalid Request"},
                        "id": data.get("id")
                    }))
                    continue

                req_id = data.get("id")
                method = data.get("method")
                params = data.get("params", {})
                resp = {"jsonrpc": "2.0", "id": req_id}
                cid = params.get("componentName")

                # Associate websocket with component
                if cid and not associated:
                    associated = cid
                    client_connections[websocket] = cid
                    active_component_sockets[cid] = websocket
                    logger.info(f"Associated WS with component: {cid}")

                # Route methods
                if method == "component.updateInput":
                    inputs = params.get("inputs")
                    if not cid or inputs is None:
                        resp["error"] = {"code": -32602, "message": "Invalid params for component.updateInput"}
                    else:
                        inst = registry.get_component_instance(cid)
                        if inst:
                            try:
                                res = await inst.update(inputs)
                                resp["result"] = res
                            except Exception as e:
                                logger.error(f"Error in update: {e}", exc_info=True)
                                resp["error"] = {"code": -32000, "message": str(e)}
                        else:
                            resp["error"] = {"code": -32001, "message": f"Component '{cid}' not found"}

                elif method == "component.getState":
                    if not cid:
                        resp["error"] = {"code": -32602, "message": "Missing componentName for getState"}
                    else:
                        inst = registry.get_component_instance(cid)
                        if inst:
                            try:
                                resp["result"] = inst.get_state()
                            except Exception as e:
                                logger.error(f"Error in getState: {e}", exc_info=True)
                                resp["error"] = {"code": -32000, "message": str(e)}
                        else:
                            resp["error"] = {"code": -32001, "message": f"Component '{cid}' not found"}

                elif method == "connection.create":
                    result = await handle_connection_create(params)
                    if "error" in result:
                        resp["error"] = result["error"]
                    else:
                        resp["result"] = result

                elif method == "connection.delete":
                    result = await handle_connection_delete(params)
                    if "error" in result:
                        resp["error"] = result["error"]
                    else:
                        resp["result"] = result

                else:
                    resp["error"] = {"code": -32601, "message": f"Method '{method}' not found"}

                await websocket.send(json.dumps(resp))
                logger.debug(f"WS sent response: {resp}")

            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None
                }))
            except Exception as e:
                err_id = data.get("id") if isinstance(data, dict) else None
                await websocket.send(json.dumps({
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": f"Internal error: {e}"},
                    "id": err_id
                }))
    except websockets.exceptions.ConnectionClosedOK:
        logger.info("Client disconnected cleanly.")
    except Exception as e:
        logger.error(f"Connection handler failed: {e}", exc_info=True)
    finally:
        # Cleanup
        if websocket in client_connections:
            cid = client_connections.pop(websocket)
            active_component_sockets.pop(cid, None)
            logger.info(f"Cleaned up WS for component: {cid}")

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
    handler = functools.partial(websocket_handler, registry=component_registry_instance)
    return await websockets.serve(
        handler, "localhost", WS_PORT,
        process_request=process_request_hook
    )

async def main():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    server = await setup_and_start_servers()
    logger.info(f"WebSocket server running on ws://localhost:{WS_PORT}")
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    asyncio.run(main())
