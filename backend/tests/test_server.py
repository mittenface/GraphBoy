import pytest
import pytest_asyncio
import asyncio
import json
import websockets
from unittest.mock import MagicMock, AsyncMock, patch, call # Added AsyncMock, call

# Attempt to import from server.py, handling potential early-stage non-existence
# try:
from backend.server import (
    WS_PORT,
    websocket_handler,
    setup_and_start_servers,
    component_registry_instance as global_component_registry, # renamed to avoid conflict
    event_bus_instance as global_event_bus_instance, # renamed
    active_connections as global_active_connections, # renamed
    handle_connection_create,
    handle_connection_delete,
    send_component_output,
    _get_event_name
)
from components.AIChatInterface.backend import AIChatInterfaceBackend # Keep for other tests
SERVER_AVAILABLE = True # Assume available, let import errors fail loudly
# except ImportError as e:
#     print(f"Test server import error: {e}")
#     SERVER_AVAILABLE = False
#     WS_PORT = 8765
#     class AIChatInterfaceBackend: pass
#     async def websocket_handler(websocket, path, chat_backend, registry): pass
#     async def setup_and_start_servers(): pass

#     # Dummy versions for parsing if server.py is incomplete
#     class DummyComponentRegistry:
#         def __init__(self): self._components = {}
#         def get_component_instance(self, name): return self._components.get(name)
#         def register_component(self, name, klass, instance=None):
#             if instance is None: instance = klass(component_id=name, send_component_output_func=None, event_bus=None)
#             self._components[name] = instance
#         def unregister_component(self, name): self._components.pop(name, None)
#         def clear(self): self._components.clear()

#     class DummyEventBus:
#         def __init__(self): self._subscribers = {}
#         async def subscribe(self, event_name, callback):
#             if event_name not in self._subscribers: self._subscribers[event_name] = []
#             self._subscribers[event_name].append(callback)
#         async def unsubscribe(self, event_name, callback):
#             if event_name in self._subscribers: self._subscribers[event_name].remove(callback)
#         async def publish(self, event_name, data=None):
#             if event_name in self._subscribers:
#                 for cb in self._subscribers[event_name]: await cb(data)
#         def clear(self): self._subscribers.clear()

#     global_component_registry = DummyComponentRegistry()
#     global_event_bus_instance = DummyEventBus()
#     global_active_connections = {}
#     async def handle_connection_create(params): return {"error": "dummy implementation"}
#     async def handle_connection_delete(params): return {"error": "dummy implementation"}
#     def send_component_output(component_id, output_name, data): pass
#     def _get_event_name(comp_id, port_name): return f"dummy::{comp_id}::{port_name}"


# Helper function to send JSON-RPC request (for existing tests)
async def send_json_rpc_request(uri, request_data):
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(request_data))
        response = await ws.recv()
        return json.loads(response)

@pytest_asyncio.fixture(scope="session") # Changed scope to session
async def test_server():
    # if not SERVER_AVAILABLE: # Removed the skip to see the actual import error
    #     pytest.skip("Skipping server tests as server.py components are not available.")

    # Use a fresh registry for each server instance in tests to avoid conflicts
    # This is tricky because server.py uses a global component_registry_instance.
    # For full isolation, server.py would need to allow injecting a registry.
    # For now, we rely on cleaning the global one.
    global_component_registry.clear()
    # Register the default AIChatInterface if setup_and_start_servers expects it
    # This part is complex as setup_and_start_servers has its own registration logic.
    # We might need to mock `ActualAIChatInterfaceBackend` or `component_registry_instance.register_component`
    # within the scope of this fixture if it's problematic.

    print("Attempting to start server in test_server fixture...")
    server_task = asyncio.create_task(setup_and_start_servers())
    # Give the server a moment to start or fail
    await asyncio.sleep(0.5) # Increased initial sleep

    if server_task.done():
        try:
            exc = server_task.exception()
            if exc:
                print(f"Server task completed with exception: {exc}")
                raise RuntimeError(f"Server task failed during startup: {exc}") from exc
            else:
                print("Server task completed without error but server did not start (no exception).")
                raise RuntimeError("Server task finished early without error, but server likely did not start.")
        except asyncio.InvalidStateError: # server_task.exception() can only be called if done
            print("Server task is done but in invalid state to get exception (should not happen).")
            raise RuntimeError("Server task done but in invalid state.")


    uri = f"ws://localhost:{WS_PORT}/"
    up = False
    print(f"Attempting to connect to server at {uri}...")
    for i in range(10): # Increased attempts slightly with logging
        await asyncio.sleep(0.3) # Slightly increased sleep between attempts
        print(f"Connection attempt {i+1}/10 to {uri}")
        try:
            async with websockets.connect(uri) as temp_ws:
                await temp_ws.ping() # Reverted to simple ping
                up = True
                print(f"Successfully connected and pinged server at {uri} on attempt {i+1}")
                break
        except (ConnectionRefusedError, websockets.exceptions.InvalidStatusCode) as e:
            print(f"Connection attempt {i+1} failed (ConnectionRefused/InvalidStatusCode): {e}")
            if server_task.done():
                print("Server task unexpectedly completed during connection attempts.")
                try:
                    exc = server_task.exception()
                    if exc: print(f"Server task exception: {exc}")
                except asyncio.InvalidStateError: pass # Already handled
                break # Stop trying if server task is done
            continue
        except Exception as e:
            print(f"Connection attempt {i+1} failed (Other Exception): {e}")
            continue

    if not up:
        print(f"WebSocket server at {uri} did not start after 10 attempts.")
        if server_task and not server_task.done():
            print("Cancelling server task...")
            server_task.cancel()
            try:
                await server_task
                print("Server task awaited after cancellation.")
            except asyncio.CancelledError:
                print("Server task successfully cancelled.")
            except Exception as e:
                print(f"Exception while awaiting cancelled server task: {e}")
        elif server_task and server_task.done():
             print("Server task was already done before cancellation attempt.")
             try:
                exc = server_task.exception()
                if exc: print(f"Server task exception (if any): {exc}")
             except asyncio.InvalidStateError: pass
        raise RuntimeError(f"WebSocket server at {uri} did not start.")

    try:
        print(f"Server at {uri} is up. Yielding URI.")
        yield uri
    finally:
        print(f"Test finished. Cleaning up server at {uri}...")
        if server_task and not server_task.done():
            print("Cancelling server task post-test...")
            server_task.cancel()
            try:
                await server_task
                print("Server task awaited after cancellation (post-test).")
            except asyncio.CancelledError:
                print("Server task successfully cancelled (post-test).")
            except Exception as e:
                print(f"Exception while awaiting cancelled server task (post-test): {e}")
        elif server_task and server_task.done():
            print("Server task was already done post-test.")

        # Final cleanup of globals
        print("Clearing global component registry and event bus in test_server fixture finally block.")
        global_component_registry.clear()
        global_event_bus_instance.clear() # Assuming EventBus has clear or similar
        global_active_connections.clear()


# Mock Component for connection tests
class MockComponent:
    def __init__(self, component_id: str, send_func=None, event_bus=None):
        self.component_id = component_id
        self.send_output_func = send_func or AsyncMock() # Mock if not provided
        self.event_bus = event_bus
        # The crucial part for testing connections:
        self.process_input = AsyncMock(name=f"{component_id}_process_input")

    async def update(self, inputs: dict): # Needed if used with full server tests
        return {"status": "mock component update"}

    def get_state(self): # Needed if used with full server tests
        return {"state": "mock component state"}


@pytest.fixture(autouse=True) # autouse=True to apply to all tests in this module/class
def clean_global_state():
    """Clears global states before each test."""
    global_component_registry.clear()
    global_event_bus_instance.clear() # Assumes EventBus has a clear method
    global_active_connections.clear()
    yield # Test runs here
    # Optional: clear again after test, though usually before is enough
    global_component_registry.clear()
    global_event_bus_instance.clear()
    global_active_connections.clear()


@pytest.mark.asyncio
# @pytest.mark.skipif(not SERVER_AVAILABLE, reason="Server components not available") # Removed skip
class TestConnectionLogic:

    async def test_connection_creation_and_data_routing(self): # Add monkeypatch if needed for global mocks
        # This test might need monkeypatch for get_port_details if strict validation is on in handle_connection_create
        # For now, assuming it passes if components are found (original test logic)
        source_comp = MockComponent("source_comp")
        target_comp = MockComponent("target_comp")
        global_component_registry.register_component("source_comp", MockComponent, instance=source_comp)
        global_component_registry.register_component("target_comp", MockComponent, instance=target_comp)

        conn_params = {
            "connectionId": "conn1",
            "sourceComponentId": "source_comp", "sourcePortName": "output1",
            "targetComponentId": "target_comp", "targetPortName": "input1"
        }
        # Mock get_port_details to allow this connection
        with patch.object(global_component_registry, 'get_port_details', side_effect=[
            {"name": "output1", "type": "output", "data_type": "any"},
            {"name": "input1", "type": "input", "data_type": "any"}
        ]):
            with patch.object(global_event_bus_instance, 'subscribe', wraps=global_event_bus_instance.subscribe) as mock_subscribe:
                result = await handle_connection_create(conn_params)

        assert result.get("status") == "success", f"Connection failed: {result.get('error')}"
        assert "conn1" in global_active_connections
        conn_details = global_active_connections["conn1"]
        assert conn_details["event_name"] == _get_event_name("source_comp", "output1")
        assert callable(conn_details["callback"])
        mock_subscribe.assert_called_once_with(conn_details["event_name"], conn_details["callback"])

        test_data = {"message": "hello world"}
        # Call send_component_output (which now uses the global event_bus_instance)
        send_component_output("source_comp", "output1", test_data)

        # Wait for the callback to be executed with a timeout
        for _ in range(100): # Poll for up to 1 second
            if target_comp.process_input.called:
                break
            await asyncio.sleep(0.01)

        target_comp.process_input.assert_awaited_once_with("input1", test_data)

    async def test_connection_deletion_stops_routing(self):
        source_comp = MockComponent("source_comp_del")
        target_comp = MockComponent("target_comp_del")
        global_component_registry.register_component("source_comp_del", MockComponent, instance=source_comp)
        global_component_registry.register_component("target_comp_del", MockComponent, instance=target_comp)

        conn_params = {
            "connectionId": "conn2",
            "sourceComponentId": "source_comp_del", "sourcePortName": "output_del",
            "targetComponentId": "target_comp_del", "targetPortName": "input_del"
        }
        # Mock get_port_details for this connection
        with patch.object(global_component_registry, 'get_port_details', side_effect=[
            {"name": "output_del", "type": "output", "data_type": "any"}, # Source
            {"name": "input_del", "type": "input", "data_type": "any"}  # Target
        ]):
            await handle_connection_create(conn_params)

        # Verify it works before deletion
        test_data_before = {"signal": "on"}
        send_component_output("source_comp_del", "output_del", test_data_before)

        for _ in range(100): # Poll for up to 1 second
            if target_comp.process_input.called:
                break
            await asyncio.sleep(0.01)
        target_comp.process_input.assert_awaited_once_with("input_del", test_data_before)
        target_comp.process_input.reset_mock() # Reset for the next assertion

        # Delete connection
        with patch.object(global_event_bus_instance, 'unsubscribe', wraps=global_event_bus_instance.unsubscribe) as mock_unsubscribe:
            del_result = await handle_connection_delete({"connectionId": "conn2"})

        assert del_result.get("status") == "success"
        assert "conn2" not in global_active_connections

        # event_name and callback were stored in active_connections, which is now deleted.
        # We need to reconstruct the event_name to check unsubscribe.
        # The callback reference might be harder to check directly unless we stored it in the test.
        expected_event_name = _get_event_name("source_comp_del", "output_del")
        # Check that unsubscribe was called with the correct event name.
        # Checking the callback precisely is tricky as it's dynamically generated.
        # We trust that handle_connection_delete retrieves the correct one.
        assert any(call_args[0][0] == expected_event_name for call_args in mock_unsubscribe.call_args_list)


        # Try sending data again
        test_data_after = {"signal": "off"}
        send_component_output("source_comp_del", "output_del", test_data_after)

        # Ensure it's NOT called; a short sleep to catch any late calls
        await asyncio.sleep(0.1)
        target_comp.process_input.assert_not_called()

    async def test_create_connection_target_component_not_found(self, monkeypatch):
        source_comp = MockComponent("source_comp_nf")
        global_component_registry.register_component("source_comp_nf", MockComponent, instance=source_comp)

        conn_params = {
            "connectionId": "conn3",
            "sourceComponentId": "source_comp_nf", "sourcePortName": "output_nf",
            "targetComponentId": "non_existent_target", "targetPortName": "input_nf"
        }
        # Mock get_port_details for source, target will cause component_instance check to fail
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "output_nf", "type": "output", "data_type": "any"},  # Source port
            None, # Target port not found (or component not found for port)
        ]))
        # Ensure get_component_instance for the target also returns None
        monkeypatch.setattr(global_component_registry, 'get_component_instance', MagicMock(return_value=None))


        result = await handle_connection_create(conn_params)
        assert result.get("error") is not None
        # The error code depends on which check fails first.
        # If port_details for target is None -> -32004
        # If port_details found but instance not -> -32001
        # Given the current server.py, get_port_details is checked first for target.
        assert result["error"]["code"] == -32004
        assert "port details not found for target port" in result["error"]["message"].lower()
        assert "conn3" not in global_active_connections

    # New tests for handle_connection_create validation
    async def test_handle_connection_create_valid(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "output", "data_type": "text"},  # Source port
            {"name": "tgt_port", "type": "input", "data_type": "text"}   # Target port
        ]))
        monkeypatch.setattr(global_component_registry, 'get_component_instance', MagicMock(return_value=MockComponent("target_comp_valid")))
        # subscribe is synchronous, so use MagicMock not AsyncMock
        mock_subscribe = MagicMock()
        monkeypatch.setattr(global_event_bus_instance, 'subscribe', mock_subscribe)

        params = {
            "connectionId": "conn_valid",
            "sourceComponentId": "src_comp", "sourcePortName": "src_port",
            "targetComponentId": "tgt_comp", "targetPortName": "tgt_port"
        }
        result = await handle_connection_create(params)

        assert result.get("status") == "success"
        assert result.get("connectionId") == "conn_valid"
        mock_subscribe.assert_called_once()
        assert "conn_valid" in global_active_connections

    async def test_handle_connection_create_invalid_source_type(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "input", "data_type": "text"}, # Invalid source type
            {"name": "tgt_port", "type": "input", "data_type": "text"}
        ]))
        params = {"connectionId": "conn_inv_src_type", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32003
        assert "source port must be an output port" in result["error"]["message"].lower()

    async def test_handle_connection_create_invalid_target_type(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "output", "data_type": "text"},
            {"name": "tgt_port", "type": "output", "data_type": "text"} # Invalid target type
        ]))
        params = {"connectionId": "conn_inv_tgt_type", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32003
        assert "target port must be an input port" in result["error"]["message"].lower()

    async def test_handle_connection_create_mismatched_data_types(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "output", "data_type": "text"},
            {"name": "tgt_port", "type": "input", "data_type": "number"} # Mismatched data type
        ]))
        params = {"connectionId": "conn_mismatch_type", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32003
        assert "data type mismatch" in result["error"]["message"].lower()

    async def test_handle_connection_create_source_port_not_found(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            None, # Source port not found
            {"name": "tgt_port", "type": "input", "data_type": "text"}
        ]))
        params = {"connectionId": "conn_src_not_found", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32004
        assert "port details not found for source port" in result["error"]["message"].lower()

    async def test_handle_connection_create_target_port_not_found(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "output", "data_type": "text"},
            None # Target port not found
        ]))
        params = {"connectionId": "conn_tgt_not_found", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32004
        assert "port details not found for target port" in result["error"]["message"].lower()

    async def test_delete_non_existent_connection(self):
        result = await handle_connection_delete({"connectionId": "conn_non_existent"})
        assert result.get("status") == "not_found"

    async def test_send_output_publishes_event_regardless_of_connection(self):
        source_comp = MockComponent("source_comp_publish")
        # No target component or connection created intentionally
        global_component_registry.register_component("source_comp_publish", MockComponent, instance=source_comp)

        test_data = {"info": "broadcast"}
        event_name = _get_event_name("source_comp_publish", "output_publish")

        with patch.object(global_event_bus_instance, 'publish', wraps=global_event_bus_instance.publish) as mock_publish:
            send_component_output("source_comp_publish", "output_publish", test_data)
            # No asyncio.sleep(0) needed before this assertion if publish itself is synchronous
            # or if we are just checking if it was called.
            # If publish is async and we need to check effects of publish, then sleep.
            # Here, we check that publish was called.
            # For send_component_output, it calls asyncio.create_task(event_bus_instance.publish(...))
            # So, we need a small sleep to allow the task to be scheduled and executed.
            await asyncio.sleep(0.01)


        mock_publish.assert_awaited_once_with(event_name, data=test_data)
        # No process_input should be called on any component as none are connected.


# --- Existing tests below, ensure they are not broken by new structure ---
@pytest.mark.asyncio
async def test_component_update_input_routes_to_chat_component(test_server, monkeypatch): # Removed SERVER_AVAILABLE check
    uri = test_server
    request_id = "comp-route-test-1"
    component_name = "AIChatInterface"
    test_inputs = {"userInput": "Testing routing"}

    mock_chat_backend = MagicMock(spec=AIChatInterfaceBackend)
    mock_chat_backend.update.return_value = {"status": "mock update called"}
    # This needs to be the global_component_registry used by the server
    # Ensure the mock_chat_backend is registered correctly if component_registry.get_component_instance is used by server
    # For this specific test, it seems get_component_instance is directly monkeypatched.
    monkeypatch.setattr(global_component_registry, 'get_component_instance', lambda name: mock_chat_backend if name == component_name else None)

    request = {"jsonrpc": "2.0", "method": "component.updateInput", "params": {"componentName": component_name, "inputs": test_inputs}, "id": request_id}
    response = await send_json_rpc_request(uri, request)

    mock_chat_backend.update.assert_called_once_with(test_inputs)
    assert response.get("id") == request_id
    assert "result" in response

@pytest.mark.asyncio
async def test_server_responds_to_ping(test_server): # Removed SERVER_AVAILABLE check
    uri = test_server
    try:
        async with websockets.connect(uri) as ws: await ws.ping()
        assert True
    except Exception as e: pytest.fail(f"Ping test failed: {e}")

@pytest.mark.asyncio
async def test_invalid_json_rpc_request(test_server): # Removed SERVER_AVAILABLE check
    uri = test_server
    response = await send_json_rpc_request(uri, {"invalid_json_rpc": True})
    assert response["error"]["code"] == -32600

@pytest.mark.asyncio
async def test_method_not_found(test_server): # Removed SERVER_AVAILABLE check
    uri = test_server
    response = await send_json_rpc_request(uri, {"jsonrpc": "2.0", "method": "nonExistent.method", "id": "mf-1"})
    assert response["error"]["code"] == -32601

# Tests for send_component_output's WebSocket part (if still relevant, or adapt)
# These tests might need adjustment if send_component_output's primary role shifts
# or if client_connections is managed differently.
# For now, assuming send_component_output still tries to send to WebSocket.

# Need to patch the server's active_component_sockets if send_component_output uses it
# if SERVER_AVAILABLE: # Assume SERVER_AVAILABLE is true for this block or manage active_component_sockets import
from backend.server import active_component_sockets
# else:
#     active_component_sockets = {}


@pytest.mark.asyncio
async def test_send_component_output_websocket_success(): # Removed SERVER_AVAILABLE check
    mock_ws = MagicMock(spec=websockets.WebSocketServerProtocol)
    mock_ws.send = AsyncMock()

    test_component_id = "test_comp_ws_send"
    output_name = "test_ws_output"
    data = {"key": "ws_value"}

    # Patch active_component_sockets used by server.py's send_component_output
    with patch('backend.server.active_component_sockets', {test_component_id: mock_ws}):
        # Also patch event_bus_instance.publish to prevent its side effects during this specific WS test
        with patch.object(global_event_bus_instance, 'publish', new_callable=AsyncMock) as mock_event_publish:
            send_component_output(test_component_id, output_name, data)
            # send_component_output now creates tasks for both ws send and event publish
            # We need to allow these tasks to run
            await asyncio.sleep(0.01)

            expected_message = json.dumps({
                "jsonrpc": "2.0",
                "method": "component.emitOutput",
                "params": {"componentId": test_component_id, "outputName": output_name, "data": data}
            })
            mock_ws.send.assert_called_once_with(expected_message)
            mock_event_publish.assert_called_once() # Check it was also called

@pytest.mark.asyncio
async def test_send_component_output_websocket_no_connection(): # Removed SERVER_AVAILABLE check
    test_component_id = "test_comp_ws_no_conn"
    # Ensure component_id is not in active_component_sockets
    with patch('backend.server.active_component_sockets', {}):
        with patch.object(global_event_bus_instance, 'publish', new_callable=AsyncMock) as mock_event_publish:
            # If send_component_output includes logging, that could be checked too.
            send_component_output(test_component_id, "some_output", {})
            await asyncio.sleep(0.01) # Allow tasks to run
            # No WebSocket send should be attempted.
            # mock_event_publish should still be called
            mock_event_publish.assert_called_once()


# The test_websocket_handler_integration_emits_output_and_cleans_up may need adjustments
# if the component registration or client_connections logic has significantly changed.
# It's a full integration test, so it's sensitive to many parts of server.py
@pytest.mark.asyncio
async def test_websocket_handler_integration_emits_output_and_cleans_up(test_server): # Removed SERVER_AVAILABLE check
    uri = test_server; client_ws = None; test_component_id = "AIChatInterface"
    # from backend.server import active_component_sockets as server_active_sockets # Already imported globally or handle here

    # This test assumes AIChatInterface is registered by setup_and_start_servers
    # and that it uses send_component_output which in turn uses global_event_bus_instance
    # and global_active_component_sockets.

    try:
        async with websockets.connect(uri) as ws:
            client_ws = ws
            update_req = {
                "jsonrpc": "2.0", "method": "component.updateInput",
                "params": {"componentName": test_component_id, "inputs": {"userInput": "Test emit", "temperature": 0.1}},
                "id": "integ-update-1"
            }
            await ws.send(json.dumps(update_req))

            # Ack for updateInput
            resp_ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert resp_ack.get("id") == "integ-update-1" and "result" in resp_ack

            # Check if ws connection stored
            assert test_component_id in server_active_sockets

            # emitOutput message
            emit_msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert emit_msg.get("method") == "component.emitOutput"
            assert emit_msg["params"].get("componentId") == test_component_id

        # After disconnect
        await asyncio.sleep(0.1) # Allow server to process disconnect
        assert test_component_id not in server_active_sockets

    except asyncio.TimeoutError: pytest.fail("Timeout waiting for WS message.")
    except Exception as e:
        if client_ws and not client_ws.closed: await client_ws.close() # Corrected .open to not .closed
        pytest.fail(f"WS integration test failed: {type(e).__name__} - {e}")

# Ensure EventBus and ComponentRegistry have clear methods if they don't already
# This is a temporary measure for the tests. Ideally, instances are passed around.
# if SERVER_AVAILABLE: # Assume SERVER_AVAILABLE is true for these or handle missing attributes
if hasattr(global_event_bus_instance, '_subscribers') and not hasattr(global_event_bus_instance, 'clear'): # Check if it's the actual instance
    def eb_clear(): global_event_bus_instance._subscribers.clear()
    global_event_bus_instance.clear = eb_clear

if hasattr(global_component_registry, '_registry') and not hasattr(global_component_registry, 'clear'): # Check if it's the actual instance
    def cr_clear(): global_component_registry._registry.clear() # Assuming internal is _registry
    global_component_registry.clear = cr_clear
# elif isinstance(global_event_bus_instance, DummyEventBus) and isinstance(global_component_registry, DummyComponentRegistry):
#     pass # Dummy versions already have clear.

# Final check for SERVER_AVAILABLE to ensure all conditional imports are handled
# if not SERVER_AVAILABLE: # Assume available
#     print("Warning: server.py components were not fully available. Some tests were skipped or used dummies.")

# It's important that the global instances used by the server functions
# (handle_connection_create, etc.) are the same ones we are clearing and patching.
# server.py currently defines these as module-level globals.
# e.g. component_registry_instance = ComponentRegistry()
# event_bus_instance = EventBus()
# active_connections = {}
# If these names in server.py are different from what's imported as global_*, tests will fail.
# The current import aliases them:
# from backend.server import component_registry as global_component_registry
# This should work if server.py uses `component_registry` as the global name.
# Based on previous steps, server.py used `component_registry_instance`, `event_bus_instance`, `active_connections`.
# The imports in this test file have been updated to reflect these names (e.g., `global_component_registry` for `component_registry_instance`).

# A final check on the global instance names:
# server.py has:
# event_bus_instance = EventBus()
# component_registry_instance = ComponentRegistry(...)
# active_connections = {}
# The test file imports these as:
# global_event_bus_instance, global_component_registry, global_active_connections
# This mapping needs to be accurate.

# Let's assume they are correctly aliased.
