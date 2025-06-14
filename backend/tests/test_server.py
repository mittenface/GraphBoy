import pytest
import pytest_asyncio
import asyncio
import json
import websockets
from unittest.mock import MagicMock, AsyncMock, patch, call

from backend.server import (
    WS_PORT,
    websocket_handler,
    setup_and_start_servers,
    component_registry_instance as global_component_registry,
    event_bus_instance as global_event_bus_instance,
    active_connections as global_active_connections,
    handle_connection_create,
    handle_connection_delete,
    send_component_output,
    _get_event_name
)
from components.AIChatInterface.backend import AIChatInterfaceBackend
SERVER_AVAILABLE = True # Assume available


# Helper function to send JSON-RPC request
async def send_json_rpc_request(uri, request_data):
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(request_data))
        response = await ws.recv()
        return json.loads(response)

@pytest_asyncio.fixture(scope="session")
async def test_server():
    print("Attempting to start server in test_server fixture...")
    # Ensure globals are clean before server starts for a new session
    # Though clean_global_state fixture should handle per-test cleaning
    global_component_registry.clear()
    global_event_bus_instance.clear()
    global_active_connections.clear()
    
    server_task = asyncio.create_task(setup_and_start_servers())
    await asyncio.sleep(0.5) # Give the server a moment to start or fail

    if server_task.done():
        try:
            exc = server_task.exception()
            if exc:
                print(f"Server task completed with exception: {exc}")
                raise RuntimeError(f"Server task failed during startup: {exc}") from exc
            else:
                print("Server task completed without error but server did not start (no exception).")
                raise RuntimeError("Server task finished early without error, but server likely did not start.")
        except asyncio.InvalidStateError:
            print("Server task is done but in invalid state to get exception (should not happen).")
            raise RuntimeError("Server task done but in invalid state.")

    uri = f"ws://localhost:{WS_PORT}/"
    up = False
    print(f"Attempting to connect to server at {uri}...")
    for i in range(10):
        await asyncio.sleep(0.3)
        print(f"Connection attempt {i+1}/10 to {uri}")
        try:
            async with websockets.connect(uri) as temp_ws:
                await temp_ws.ping()
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
                except asyncio.InvalidStateError: pass
                break
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

    print(f"Server at {uri} is up. Yielding URI.")
    try:
        yield uri
    finally:
        print(f"Test session finished. Cleaning up server at {uri}...")
        if server_task and not server_task.done():
            print("Cancelling server task post-session...")
            server_task.cancel()
            try:
                await server_task
                print("Server task awaited after cancellation (post-session).")
            except asyncio.CancelledError:
                print("Server task successfully cancelled (post-session).")
            except Exception as e:
                print(f"Exception while awaiting cancelled server task (post-session): {e}")
        elif server_task and server_task.done():
            print("Server task was already done post-session.")
        
        # Final cleanup of globals after all tests in session are done
        print("Clearing global component registry and event bus in test_server fixture finally block (session scope).")
        global_component_registry.clear()
        global_event_bus_instance.clear()
        global_active_connections.clear()


class MockComponent:
    def __init__(self, component_id: str, send_func=None, event_bus=None):
        self.component_id = component_id
        self.send_output_func = send_func or AsyncMock()
        self.event_bus = event_bus
        self.process_input = AsyncMock(name=f"{component_id}_process_input")

    async def update(self, inputs: dict):
        return {"status": "mock component update"}

    def get_state(self):
        return {"state": "mock component state"}


@pytest.fixture(autouse=True)
def clean_global_state():
    """Clears global states before each test."""
    # Note: For session-scoped server, this cleans for each test but server runs once.
    # This is good for ensuring test isolation for global dictionaries like active_connections.
    global_component_registry.clear() # Clears manifests, instances, port_details
    global_event_bus_instance.clear() # Clears subscribers
    global_active_connections.clear() # Clears active connections
    
    # Re-register AIChatInterface as it's done in server.py's setup_and_start_servers
    # This ensures it's available for tests that might expect it.
    # This is a simplified version of what's in server.py's setup_and_start_servers
    component_id = "AIChatInterface" 
    # Check if it's already registered by the server fixture to avoid issues, though clear() should remove it
    if not global_component_registry.get_component_instance(component_id):
        inst = AIChatInterfaceBackend(
            component_id=component_id,
            send_component_output_func=send_component_output, # Real function
            event_bus=global_event_bus_instance
        )
        global_component_registry.register_component(
            name=component_id,
            component_class=AIChatInterfaceBackend,
            instance=inst
        )
    yield
    # Clean again after test
    global_component_registry.clear()
    global_event_bus_instance.clear()
    global_active_connections.clear()


@pytest.mark.asyncio
class TestConnectionLogic:

    async def test_connection_creation_and_data_routing(self, monkeypatch):
        source_comp = MockComponent("source_comp")
        target_comp = MockComponent("target_comp")
        global_component_registry.register_component("source_comp", MockComponent, instance=source_comp)
        global_component_registry.register_component("target_comp", MockComponent, instance=target_comp)

        conn_params = {
            "connectionId": "conn1",
            "sourceComponentId": "source_comp", "sourcePortName": "output1",
            "targetComponentId": "target_comp", "targetPortName": "input1"
        }
        
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "output1", "type": "output", "data_type": "text"},
            {"name": "input1", "type": "input", "data_type": "text"}
        ]))
        # Ensure target_instance is found after port validation
        monkeypatch.setattr(global_component_registry, 'get_component_instance', MagicMock(side_effect=lambda comp_id: target_comp if comp_id == "target_comp" else source_comp if comp_id == "source_comp" else None ))

        with patch.object(global_event_bus_instance, 'subscribe', wraps=global_event_bus_instance.subscribe) as mock_subscribe:
            result = await handle_connection_create(conn_params)

        assert result.get("status") == "success", f"Connection failed: {result.get('error')}"
        assert "conn1" in global_active_connections
        conn_details = global_active_connections["conn1"]
        assert conn_details["event_name"] == _get_event_name("source_comp", "output1")
        assert callable(conn_details["callback"])
        mock_subscribe.assert_called_once_with(conn_details["event_name"], conn_details["callback"])

        test_data = {"message": "hello world"}
        send_component_output("source_comp", "output1", test_data)
        
        for _ in range(100): 
            if target_comp.process_input.called:
                break
            await asyncio.sleep(0.01)
        target_comp.process_input.assert_awaited_once_with("input1", test_data)

    async def test_connection_deletion_stops_routing(self, monkeypatch):
        source_comp = MockComponent("source_comp_del")
        target_comp = MockComponent("target_comp_del")
        global_component_registry.register_component("source_comp_del", MockComponent, instance=source_comp)
        global_component_registry.register_component("target_comp_del", MockComponent, instance=target_comp)

        conn_params = {
            "connectionId": "conn2",
            "sourceComponentId": "source_comp_del", "sourcePortName": "output_del",
            "targetComponentId": "target_comp_del", "targetPortName": "input_del"
        }
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "output_del", "type": "output", "data_type": "any"}, 
            {"name": "input_del", "type": "input", "data_type": "any"}
        ]))
        monkeypatch.setattr(global_component_registry, 'get_component_instance', MagicMock(side_effect=lambda comp_id: target_comp if comp_id == "target_comp_del" else source_comp if comp_id == "source_comp_del" else None))

        await handle_connection_create(conn_params)

        test_data_before = {"signal": "on"}
        send_component_output("source_comp_del", "output_del", test_data_before)
        for _ in range(100):
            if target_comp.process_input.called:
                break
            await asyncio.sleep(0.01)
        target_comp.process_input.assert_awaited_once_with("input_del", test_data_before)
        target_comp.process_input.reset_mock()

        with patch.object(global_event_bus_instance, 'unsubscribe', wraps=global_event_bus_instance.unsubscribe) as mock_unsubscribe:
            del_result = await handle_connection_delete({"connectionId": "conn2"})

        assert del_result.get("status") == "success"
        assert "conn2" not in global_active_connections
        expected_event_name = _get_event_name("source_comp_del", "output_del")
        assert any(call_args[0][0] == expected_event_name for call_args in mock_unsubscribe.call_args_list)

        test_data_after = {"signal": "off"}
        send_component_output("source_comp_del", "output_del", test_data_after)
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
        
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "output_nf", "type": "output", "data_type": "any"},
            None, 
        ]))
        monkeypatch.setattr(global_component_registry, 'get_component_instance', MagicMock(return_value=None))
        
        result = await handle_connection_create(conn_params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32004 
        assert "port details not found for target port" in result["error"]["message"].lower()
        assert "conn3" not in global_active_connections

    async def test_handle_connection_create_valid(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "output", "data_type": "text"},
            {"name": "tgt_port", "type": "input", "data_type": "text"}
        ]))
        monkeypatch.setattr(global_component_registry, 'get_component_instance', MagicMock(return_value=MockComponent("target_comp_valid")))
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
            {"name": "src_port", "type": "input", "data_type": "text"}, 
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
            {"name": "tgt_port", "type": "output", "data_type": "text"}
        ]))
        params = {"connectionId": "conn_inv_tgt_type", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32003
        assert "target port must be an input port" in result["error"]["message"].lower()

    async def test_handle_connection_create_mismatched_data_types(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            {"name": "src_port", "type": "output", "data_type": "text"},
            {"name": "tgt_port", "type": "input", "data_type": "number"}
        ]))
        params = {"connectionId": "conn_mismatch_type", "sourceComponentId": "s", "sourcePortName": "s_p", "targetComponentId": "t", "targetPortName": "t_p"}
        result = await handle_connection_create(params)
        assert result.get("error") is not None
        assert result["error"]["code"] == -32003
        assert "data type mismatch" in result["error"]["message"].lower()

    async def test_handle_connection_create_source_port_not_found(self, monkeypatch):
        monkeypatch.setattr(global_component_registry, 'get_port_details', MagicMock(side_effect=[
            None, 
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
            None 
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
        global_component_registry.register_component("source_comp_publish", MockComponent, instance=source_comp)

        test_data = {"info": "broadcast"}
        event_name = _get_event_name("source_comp_publish", "output_publish")

        with patch.object(global_event_bus_instance, 'publish', wraps=global_event_bus_instance.publish) as mock_publish:
            send_component_output("source_comp_publish", "output_publish", test_data)
            await asyncio.sleep(0.01)

        mock_publish.assert_awaited_once_with(event_name, data=test_data)


@pytest.mark.asyncio
async def test_component_update_input_routes_to_chat_component(test_server, monkeypatch):
    uri = test_server
    request_id = "comp-route-test-1"
    component_name = "AIChatInterface" # This is the one registered by test_server/setup_and_start_servers
    test_inputs = {"userInput": "Testing routing"}

    # We need to mock the *instance* that the server uses for "AIChatInterface"
    # The clean_global_state fixture now re-registers a real AIChatInterfaceBackend.
    # So we patch its update method, or get that instance and patch it.
    actual_instance = global_component_registry.get_component_instance(component_name)
    assert actual_instance is not None, "AIChatInterface should be registered by clean_global_state"
    
    # Patch the 'update' method of the actual instance
    with patch.object(actual_instance, 'update', new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"status": "mock update called"}

        request = {"jsonrpc": "2.0", "method": "component.updateInput", 
                   "params": {"componentName": component_name, "inputs": test_inputs}, 
                   "id": request_id}
        response = await send_json_rpc_request(uri, request)

        mock_update.assert_called_once_with(test_inputs)
        assert response.get("id") == request_id
        assert "result" in response
        assert response["result"] == {"status": "mock update called"}


@pytest.mark.asyncio
async def test_server_responds_to_ping(test_server):
    uri = test_server
    try:
        async with websockets.connect(uri) as ws: await ws.ping()
        assert True
    except Exception as e: pytest.fail(f"Ping test failed: {e}")

@pytest.mark.asyncio
async def test_invalid_json_rpc_request(test_server):
    uri = test_server
    response = await send_json_rpc_request(uri, {"invalid_json_rpc": True})
    assert response["error"]["code"] == -32600

@pytest.mark.asyncio
async def test_method_not_found(test_server):
    uri = test_server
    response = await send_json_rpc_request(uri, {"jsonrpc": "2.0", "method": "nonExistent.method", "id": "mf-1"})
    assert response["error"]["code"] == -32601

from backend.server import active_component_sockets

@pytest.mark.asyncio
async def test_send_component_output_websocket_success():
    mock_ws = MagicMock(spec=websockets.WebSocketServerProtocol)
    mock_ws.send = AsyncMock()

    test_component_id = "test_comp_ws_send"
    output_name = "test_ws_output"
    data = {"key": "ws_value"}

    with patch('backend.server.active_component_sockets', {test_component_id: mock_ws}):
        with patch.object(global_event_bus_instance, 'publish', new_callable=AsyncMock) as mock_event_publish:
            send_component_output(test_component_id, output_name, data)
            await asyncio.sleep(0.01)

            expected_message = json.dumps({
                "jsonrpc": "2.0",
                "method": "component.emitOutput",
                "params": {"componentId": test_component_id, "outputName": output_name, "data": data}
            })
            mock_ws.send.assert_called_once_with(expected_message)
            mock_event_publish.assert_called_once()

@pytest.mark.asyncio
async def test_send_component_output_websocket_no_connection():
    test_component_id = "test_comp_ws_no_conn"
    with patch('backend.server.active_component_sockets', {}):
        with patch.object(global_event_bus_instance, 'publish', new_callable=AsyncMock) as mock_event_publish:
            send_component_output(test_component_id, "some_output", {})
            await asyncio.sleep(0.01)
            mock_event_publish.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_handler_integration_emits_output_and_cleans_up(test_server):
    uri = test_server; client_ws = None; test_component_id = "AIChatInterface"
    
    try:
        async with websockets.connect(uri) as ws:
            client_ws = ws
            # Associate this client with AIChatInterface for server to know where to send emitOutput
            # This can be done via a special message or by path, here we assume path or prior message.
            # For this test, the server's `setup_and_start_servers` already registers "AIChatInterface".
            # We need to ensure this WS connection becomes associated with it.
            # A simple way is to send an initial message that includes componentName.
            # The test_component_update_input_routes_to_chat_component does this.
            # Here, we'll rely on the server's setup_and_start_servers registering the component
            # and the component's backend logic calling send_component_output correctly.
            
            # Send a message that will trigger an output from AIChatInterface
            update_req = {
                "jsonrpc": "2.0", "method": "component.updateInput",
                "params": {"componentName": test_component_id, "inputs": {"userInput": "Test emit", "temperature": 0.1}},
                "id": "integ-update-1"
            }
            await ws.send(json.dumps(update_req))

            # Ack for updateInput
            resp_ack_str = await asyncio.wait_for(ws.recv(), timeout=3.0)
            resp_ack = json.loads(resp_ack_str)
            assert resp_ack.get("id") == "integ-update-1"
            assert "result" in resp_ack, f"Result missing in ack: {resp_ack_str}"


            # emitOutput message (expecting responseText or responseStream)
            # This depends on AIChatInterfaceBackend's actual output behavior
            emit_msg_str = await asyncio.wait_for(ws.recv(), timeout=3.0)
            emit_msg = json.loads(emit_msg_str)
            assert emit_msg.get("method") == "component.emitOutput"
            assert emit_msg["params"].get("componentId") == test_component_id
            # Check for one of the possible outputs
            assert emit_msg["params"].get("outputName") in ["responseText", "responseStream", "error"], f"Unexpected output name: {emit_msg_str}"

        # After disconnect
        await asyncio.sleep(0.1) 
        assert test_component_id not in active_component_sockets # Check it's removed from active_component_sockets

    except asyncio.TimeoutError: pytest.fail("Timeout waiting for WS message.")
    except Exception as e:
        if client_ws and not client_ws.closed: await client_ws.close()
        pytest.fail(f"WS integration test failed: {type(e).__name__} - {e}")


if hasattr(global_event_bus_instance, '_subscribers') and not hasattr(global_event_bus_instance, 'clear'):
    def eb_clear(): global_event_bus_instance._subscribers.clear()
    global_event_bus_instance.clear = eb_clear

if hasattr(global_component_registry, 'manifests') and not hasattr(global_component_registry, 'clear'): # Check if it's the actual instance
    def cr_clear(): 
        global_component_registry.manifests.clear()
        if hasattr(global_component_registry, 'instances'): global_component_registry.instances.clear()
        if hasattr(global_component_registry, 'port_details'): global_component_registry.port_details.clear()
    global_component_registry.clear = cr_clear
