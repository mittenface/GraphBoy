import pytest
import pytest_asyncio
import asyncio
import json
import websockets
from unittest.mock import MagicMock, patch

# Attempt to import from server.py, handling potential early-stage non-existence
try:
    # Import component_registry_instance instead of component_registry
    from backend.server import WS_PORT, websocket_handler, setup_and_start_servers, component_registry_instance, ActualAIChatInterfaceBackend
    SERVER_AVAILABLE = True
except ImportError as e:
    print(f"DEBUG: Caught ImportError in test_server.py: {e}") # Debug print
    SERVER_AVAILABLE = False
    # Define WS_PORT here if server.py is not available, so tests can be parsed
    WS_PORT = 8765
    # Define dummy classes/functions if server components are not available
    class ActualAIChatInterfaceBackend: pass
    async def websocket_handler(websocket, path, chat_backend, registry): pass
    async def setup_and_start_servers(): pass
    # Define ComponentRegistryDummy and component_registry_instance for the SERVER_AVAILABLE = False case
    class ComponentRegistryDummy:
        def get_component_instance(self, name): return None
        def register_component(self, name, klass, instance=None): pass
    component_registry_instance = ComponentRegistryDummy()


from backend.component_registry import ComponentRegistry # This should be the actual one

# Helper function to send JSON-RPC request (should be present in the test file)
async def send_json_rpc_request(uri, request_data):
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(request_data))
        response = await ws.recv()
        return json.loads(response)

@pytest_asyncio.fixture # Changed from @pytest.fixture
async def test_server():
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping server tests as server.py components are not available.")

    # Ensure the registry is clean for each test run if it's a global instance
    # This might involve a reset method on ComponentRegistry or re-initialization
    # For now, we assume component_registry_instance is managed by setup_and_start_servers

    server_process = None
    try:
        # Start the server
        server_instance = await setup_and_start_servers() # setup_and_start_servers returns the server object
        server_task = asyncio.create_task(server_instance.serve_forever()) # Keep server running in a task


        # Wait for the server to be ready
        uri = f"ws://localhost:{WS_PORT}/"
        up = False
        for _ in range(20): # Increased attempts for server readiness
            await asyncio.sleep(0.2)
            try:
                async with websockets.connect(uri) as temp_ws:
                    await temp_ws.ping()
                    up = True
                    break
            except (ConnectionRefusedError, websockets.exceptions.InvalidStatusCode):
                continue
            except Exception as e:
                print(f"Test server readiness check failed during connect: {e}")
                continue

        if not up:
            if not server_task.done():
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    print("Server task (serve_forever) cancelled during setup failure.")
            server_instance.close()
            await server_instance.wait_closed()
            raise RuntimeError(f"WebSocket server at {uri} did not start in time.")

        yield uri

        # Teardown: Stop the server
        if not server_task.done():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                print("Server task (serve_forever) cancelled successfully during teardown.")

        server_instance.close()
        await server_instance.wait_closed()
        print("Server closed and awaited.")


    except Exception as e:
        pytest.fail(f"Test server fixture setup failed: {e}")
    finally:
        # Ensure any server task is cancelled, even if setup failed partway
        if 'server_task' in locals() and server_task and not server_task.done():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        if 'server_instance' in locals():
            server_instance.close()
            try:
                await server_instance.wait_closed()
            except Exception: # Ignore errors during final cleanup
                pass


@pytest.mark.asyncio
async def test_component_update_input_routes_to_chat_component(test_server, monkeypatch):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")

    uri = test_server # Use the URI from the fixture
    request_id = "comp-route-test-1"
    component_name = "AIChatInterface" # This must match the one registered in server.py
    test_inputs = {"userInput": "Testing routing", "temperature": 0.5, "maxTokens": 50}

    # 1. Set up a mock AIChatInterfaceBackend instance
    # Spec now uses ActualAIChatInterfaceBackend imported from backend.server (which is an alias)
    # or ideally from components.AIChatInterface.backend directly.
    # For now, using the one imported from backend.server for minimal changes to imports here.
    mock_chat_backend = MagicMock(spec=ActualAIChatInterfaceBackend)
    # Configure the mock update method to return a serializable dictionary
    mock_chat_backend.update.return_value = {"status": "mock update called", "responseText": "mocked response from update"}
    # Removed: mock_chat_backend.get_component_id.return_value = "AIChatInterface" (method doesn't exist on spec)


    # 2. Patch ComponentRegistry.get_component_instance
    # We need to access the registry instance that is used by the server's websocket_handler.
    # If component_registry is imported directly from server, we can patch that.

    # Get the actual registry instance used by the server.
    # This relies on `component_registry_instance` being the actual instance used by `setup_and_start_servers`.
    # If `setup_and_start_servers` creates its own registry, this patching won't affect it.
    # The server.py creates a global `component_registry_instance` and `setup_and_start_servers` uses it.

    original_get_component_instance = component_registry_instance.get_component_instance

    def mock_get_component_instance(name): # Changed from method to function
        if name == component_name:
            return mock_chat_backend
        # For other components, you might want to call the original method
        # or return another appropriate mock/real instance.
        return original_get_component_instance(name)

    monkeypatch.setattr(component_registry_instance, 'get_component_instance', mock_get_component_instance)

    # 3. Prepare and send the WebSocket request
    request = {
        "jsonrpc": "2.0",
        "method": "component.updateInput",
        "params": {
            "componentName": component_name,
            "inputs": test_inputs
        },
        "id": request_id
    }

    response = None
    try:
        response = await send_json_rpc_request(uri, request)

        # 4. Assertions
        # Check that the mock_chat_backend.update was called correctly
        mock_chat_backend.update.assert_called_once_with(test_inputs)

        # Check the server's response
        assert response is not None, "Response was None"
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id

        # Check for error field in response before asserting result
        if "error" in response:
            pytest.fail(f"Server returned an error: {response['error']}")

        assert "result" in response, "Response missing 'result' field."
        assert response["result"] == mock_chat_backend.update.return_value

    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except websockets.exceptions.ConnectionClosedError as e:
        pytest.fail(f"Connection closed unexpectedly: {e}. Server log might have details. Response: {response}")
    except Exception as e:
        pytest.fail(f"Test failed: {type(e).__name__} - {e}. Response: {response}")
    finally:
        # Clean up the patch
        monkeypatch.undo()

# Example of another test that might exist (to ensure the overwrite doesn't remove everything)
@pytest.mark.asyncio
async def test_server_responds_to_ping(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")
    uri = test_server
    try:
        async with websockets.connect(uri) as ws:
            await ws.ping()
            # Pong is handled automatically by websockets library,
            # if ping is successful, connection is good.
            assert True # If ping doesn't raise an exception, it's good.
    except Exception as e:
        pytest.fail(f"Ping test failed: {e}")

# A simple test to ensure basic JSON-RPC invalid request is handled
@pytest.mark.asyncio
async def test_invalid_json_rpc_request(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")
    uri = test_server
    request = {"invalid_json_rpc": True} # Not a valid JSON-RPC request

    response = await send_json_rpc_request(uri, request)

    assert response.get("jsonrpc") == "2.0"
    assert "error" in response
    assert response["error"]["code"] == -32600 # Invalid Request
    assert response.get("id") is None # Or matches request id if provided, but this one is None

@pytest.mark.asyncio
async def test_method_not_found(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")
    uri = test_server
    request_id = "method-not-found-test-1"
    request = {
        "jsonrpc": "2.0",
        "method": "nonExistent.method",
        "params": {},
        "id": request_id
    }
    response = await send_json_rpc_request(uri, request)
    assert response.get("jsonrpc") == "2.0"
    assert response.get("id") == request_id
    assert "error" in response
    assert response["error"]["code"] == -32601 # Method not found


# --- Tests for send_component_output and client_connections ---

    # We need to import send_component_output, client_connections, active_component_sockets from backend.server
# To do this safely if SERVER_AVAILABLE is False, we can define dummies or skip
if SERVER_AVAILABLE:
        from backend.server import send_component_output, client_connections, handle_connection_create, active_component_sockets # Added active_component_sockets
        from backend.component_registry import ComponentRegistry

else:
    async def send_component_output(component_id, output_name, data): pass
    async def handle_connection_create(params): pass
    client_connections = {}
    active_component_sockets = {} # Dummy for active_component_sockets

# AsyncMock might be needed if not already available via pytest/unittest.mock
from unittest.mock import AsyncMock


# --- Test Class for Connection Validation ---

@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_allow_text_to_text_connection(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "srcPort", "type": "text"}]}},  # Source Manifest
        {"nodes": {"inputs": [{"name": "tgtPort", "type": "text"}]}}   # Target Manifest
    ]
    params = {
        "connectionId": "conn1",
        "sourceComponentId": "srcComp", "sourcePortName": "srcPort",
        "targetComponentId": "tgtComp", "targetPortName": "tgtPort"
    }
    result = await handle_connection_create(params)
    assert result.get("status") == "success"
    assert "error" not in result
    assert mock_registry_instance.get_component_manifest.call_count == 2

@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_prevent_output_to_output_connection(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "srcPort", "type": "output"}]}}, # Source Manifest
        {"nodes": {"inputs": [{"name": "tgtPort", "type": "output"}]}}    # Target Manifest
    ]
    params = {
        "connectionId": "conn2",
        "sourceComponentId": "srcComp", "sourcePortName": "srcPort",
        "targetComponentId": "tgtComp", "targetPortName": "tgtPort"
    }
    result = await handle_connection_create(params)
    assert "error" in result
    assert result["error"]["code"] == -32002
    assert "Output-to-output connections are not allowed" in result["error"]["message"]
    assert mock_registry_instance.get_component_manifest.call_count == 2

@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_allow_other_connection_types(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    # Example: text to generic_type
    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "srcPort", "type": "text"}]}},      # Source Manifest
        {"nodes": {"inputs": [{"name": "tgtPort", "type": "generic_type"}]}} # Target Manifest
    ]
    params = {
        "connectionId": "conn3",
        "sourceComponentId": "srcComp", "sourcePortName": "srcPort",
        "targetComponentId": "tgtComp", "targetPortName": "tgtPort"
    }
    result = await handle_connection_create(params)
    assert result.get("status") == "success"
    assert "error" not in result
    mock_registry_instance.get_component_manifest.assert_any_call("srcComp")
    mock_registry_instance.get_component_manifest.assert_any_call("tgtComp")

    # Example: generic_type to text
    mock_registry_instance.reset_mock()
    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "srcPort", "type": "generic_type"}]}}, # Source Manifest
        {"nodes": {"inputs": [{"name": "tgtPort", "type": "text"}]}}        # Target Manifest
    ]
    params_2 = {
        "connectionId": "conn4",
        "sourceComponentId": "srcComp2", "sourcePortName": "srcPort",
        "targetComponentId": "tgtComp2", "targetPortName": "tgtPort"
    }
    result_2 = await handle_connection_create(params_2)
    assert result_2.get("status") == "success"
    assert "error" not in result_2
    mock_registry_instance.get_component_manifest.assert_any_call("srcComp2")
    mock_registry_instance.get_component_manifest.assert_any_call("tgtComp2")


@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_connection_with_missing_source_manifest(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    mock_registry_instance.get_component_manifest.side_effect = [
        None,  # Source Manifest
        {"nodes": {"inputs": [{"name": "tgtPort", "type": "text"}]}}   # Target Manifest
    ]
    params = {
        "connectionId": "conn5",
        "sourceComponentId": "srcCompMissing", "sourcePortName": "srcPort",
        "targetComponentId": "tgtComp", "targetPortName": "tgtPort"
    }
    result = await handle_connection_create(params)
    assert result.get("status") == "success" # Allowed with warning
    assert "error" not in result
    mock_registry_instance.get_component_manifest.assert_any_call("srcCompMissing")
    mock_registry_instance.get_component_manifest.assert_any_call("tgtComp")


@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_connection_with_missing_target_manifest(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "srcPort", "type": "text"}]}},  # Source Manifest
        None   # Target Manifest
    ]
    params = {
        "connectionId": "conn6",
        "sourceComponentId": "srcComp", "sourcePortName": "srcPort",
        "targetComponentId": "tgtCompMissing", "targetPortName": "tgtPort"
    }
    result = await handle_connection_create(params)
    assert result.get("status") == "success" # Allowed with warning
    assert "error" not in result
    mock_registry_instance.get_component_manifest.assert_any_call("srcComp")
    mock_registry_instance.get_component_manifest.assert_any_call("tgtCompMissing")

@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_connection_with_missing_source_port(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "otherPort", "type": "text"}]}},  # Source Manifest with different port
        {"nodes": {"inputs": [{"name": "tgtPort", "type": "text"}]}}   # Target Manifest
    ]
    params = {
        "connectionId": "conn7",
        "sourceComponentId": "srcComp", "sourcePortName": "missingSrcPort",
        "targetComponentId": "tgtComp", "targetPortName": "tgtPort"
    }
    result = await handle_connection_create(params)
    assert result.get("status") == "success" # Allowed with warning
    assert "error" not in result
    mock_registry_instance.get_component_manifest.assert_any_call("srcComp")
    mock_registry_instance.get_component_manifest.assert_any_call("tgtComp")


@pytest.mark.asyncio
@patch('backend.server.component_registry_instance', new_callable=MagicMock)
async def test_connection_with_missing_target_port(mock_registry_instance):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available.")

    mock_registry_instance.get_component_manifest.side_effect = [
        {"nodes": {"outputs": [{"name": "srcPort", "type": "text"}]}},  # Source Manifest
        {"nodes": {"inputs": [{"name": "otherPort", "type": "text"}]}}   # Target Manifest with different port
    ]
    params = {
        "connectionId": "conn8",
        "sourceComponentId": "srcComp", "sourcePortName": "srcPort",
        "targetComponentId": "tgtComp", "targetPortName": "missingTgtPort"
    }
    result = await handle_connection_create(params)
    assert result.get("status") == "success" # Allowed with warning
    assert "error" not in result
    mock_registry_instance.get_component_manifest.assert_any_call("srcComp")
    mock_registry_instance.get_component_manifest.assert_any_call("tgtComp")


@pytest.mark.asyncio
async def test_send_component_output_success():
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available for send_component_output.")

    mock_ws = MagicMock(spec=websockets.WebSocketServerProtocol)
    mock_ws.send = AsyncMock() # Use AsyncMock for awaitable .send()

    test_component_id = "test_comp_id_send"
    output_name = "test_output"
    data = {"key": "value"}

    # Patch active_component_sockets for this test, as this is what send_component_output uses
    with patch.dict(active_component_sockets, {test_component_id: mock_ws}, clear=True):
        task = send_component_output(test_component_id, output_name, data) # Removed await here
        await task # Ensure the task completes

        expected_message = json.dumps({
            "jsonrpc": "2.0",
            "method": "component.emitOutput",
            "params": {
                "componentId": test_component_id,
                "outputName": output_name,
                "data": data
            }
        })
        mock_ws.send.assert_called_once_with(expected_message)

@pytest.mark.asyncio
async def test_send_component_output_no_connection():
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping as server.py components are not available for send_component_output.")

    mock_ws_send = AsyncMock() # To ensure no send is attempted

    test_component_id = "test_comp_id_no_connection"
    # Ensure the component_id is not in active_component_sockets
    with patch.dict(active_component_sockets, {}, clear=True):
        # To check logs, we would need to patch 'logging.getLogger.warning' or similar
        # For simplicity, we're just ensuring it doesn't crash and no send is attempted.
        # send_component_output now returns a completed dummy task if no websocket, so it's awaitable.
        task = send_component_output(test_component_id, "some_output", {}) # Removed await here
        await task # Await the dummy task
        # mock_ws_send should not be called on any WebSocket mock because none should be found.
        # This test implicitly checks that it doesn't raise an error when component_id is not found.


@pytest.mark.asyncio
async def test_websocket_handler_integration_emits_output_and_cleans_up(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")

    uri = test_server
    client_ws = None
    test_component_id = "AIChatInterface" # This is the componentName expected by the handler

    # Ensure client_connections and active_component_sockets are imported from backend.server for inspection
    # Note: This inspects the global dictionaries from the running server.
    # This can be flaky if tests run in parallel or if server state is not perfectly isolated.
    from backend.server import client_connections as server_client_connections
    from backend.server import active_component_sockets as server_active_sockets

    try:
        async with websockets.connect(uri) as ws:
            client_ws = ws # Keep a reference for checking connection state later
            # 1. Send component.updateInput to trigger backend logic and populate client_connections
            request_id_update = "integration-update-1"
            user_input = "Test emit output"
            update_request = {
                "jsonrpc": "2.0",
                "method": "component.updateInput",
                "params": {
                    "componentName": test_component_id,
                    "inputs": {"userInput": user_input, "temperature": 0.1, "maxTokens": 10}
                },
                "id": request_id_update
            }
            await ws.send(json.dumps(update_request))

            # 2. Receive messages. Order might vary: could be emitOutput first, then updateInput ack, or vice-versa.
            # We'll try to receive two messages and check their types.
            received_messages = []
            for _ in range(2): # Expecting two messages: updateInput ack and emitOutput
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=5.0) # Increased timeout
                    received_messages.append(json.loads(raw_msg))
                except asyncio.TimeoutError:
                    # If we time out, it might be because only one message was sent (e.g. error case)
                    # or server is slow. Break and let assertions handle it.
                    break

            update_ack_received = False
            emit_output_received = False

            for msg in received_messages:
                if msg.get("id") == request_id_update and "result" in msg:
                    assert msg["result"]["status"] == "success"
                    update_ack_received = True
                elif msg.get("method") == "component.emitOutput":
                    params = msg.get("params", {})
                    assert params.get("componentId") == test_component_id
                    assert params.get("outputName") in ["responseText", "responseStream", "error"]
                    assert "data" in params
                    emit_output_received = True

            assert update_ack_received, "Acknowledgment for component.updateInput not received or incorrect."
            assert emit_output_received, "component.emitOutput message not received or incorrect."

            # Check if connection was stored
            # client_connections stores ws -> component_id, so check values
            assert test_component_id in server_client_connections.values()
            # active_component_sockets stores component_id -> ws
            assert test_component_id in server_active_sockets
            assert server_active_sockets[test_component_id] is not None


            # 3. (Original step 3 is now part of the loop above)
            # The following lines are removed as emit_output_message is not necessarily defined here,
            # and these checks are implicitly covered by the loop processing received_messages.
            # assert "params" in emit_output_message
            # params = emit_output_message["params"]
            # assert params.get("componentId") == test_component_id
            # # Based on AIChatInterfaceBackend mock LLM, it should be responseStream
            # assert params.get("outputName") in ["responseText", "responseStream", "error"]
            # # Verify data structure if possible, e.g. params.get("data") is not None
            # assert "data" in params

            # Connection should still be there
            assert test_component_id in server_active_sockets # Check active_sockets as it's more direct for component_id key

        # 4. After 'async with ws:' block, connection is closed.
        # Wait a moment for server to process disconnection if needed
        await asyncio.sleep(0.1)

        # Verify cleanup: component_id should be removed from active_component_sockets
        assert test_component_id not in server_active_sockets, \
            f"{test_component_id} was not removed from server_active_sockets after disconnect."

    except asyncio.TimeoutError:
        pytest.fail("Test timed out waiting for WebSocket message.")
    except Exception as e:
        # If client_ws exists and is not closed, try to close it gracefully on error
        if client_ws and not client_ws.closed: # Changed from .open to .closed
            await client_ws.close()
        pytest.fail(f"WebSocket integration test failed: {type(e).__name__} - {e}")
