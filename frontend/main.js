// WebSocket connection setup
console.log('[WebSocket] Setting up WebSocket connection...');
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsHost = window.location.hostname; // Get hostname without port
const wsPort = 8080; // WebSocket server port
const wsUrl = `${wsProtocol}//${wsHost}:${wsPort}`;

console.log(`[WebSocket] Attempting to connect to: ${wsUrl}`);
const socket = new WebSocket(wsUrl);

socket.onopen = function(event) {
  console.log('[WebSocket] Connection OPENED:', event);
};

socket.onerror = function(event) {
  console.error('[WebSocket] Error:', event);
};

socket.onclose = function(event) {
  console.log('[WebSocket] Connection CLOSED:', event);
  if (event.wasClean) {
    console.log(`[WebSocket] Closed cleanly, code=${event.code}, reason=${event.reason}`);
  } else {
    console.error('[WebSocket] Connection died (e.g., server process killed or network down)');
  }
};

// Debounce utility function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

socket.onmessage = function(event) {
  console.log('[WebSocket] Message received:', event.data);
  try {
    const parsedMessage = JSON.parse(event.data);
    console.log('[WebSocket] Parsed message:', parsedMessage);

    if (parsedMessage.method === "v1.connection.load") { // Versioned
      if (parsedMessage.params) {
        renderLoadedConnection(parsedMessage.params);
      } else {
        console.error('[WebSocket] v1.connection.load message received without params:', parsedMessage);
      }
    }
    // Potentially handle other backend responses here, e.g., component.emitOutput
    else if (parsedMessage.method === "component.emitOutput") {
        // Example: Find component and update its visual state or display data
        const componentId = parsedMessage.params.componentId;
        const outputName = parsedMessage.params.outputName;
        const data = parsedMessage.params.data;
        console.log(`[WebSocket] Received component.emitOutput for ${componentId} - ${outputName}:`, data);

        // Find the component on the stage
        const componentGroup = mainStage.findOne('#' + componentId);
        if (componentGroup) {
            // Find a text node within the component to display the data, or create one
            let dataDisplay = componentGroup.findOne('.data-display');
            if (!dataDisplay) {
                dataDisplay = new Konva.Text({
                    x: 5, // Adjust position as needed
                    y: componentGroup.findOne('Rect').height() + 5, // Below the main rect
                    text: `Output ${outputName}: ${JSON.stringify(data)}`,
                    fontSize: 10,
                    fill: 'black',
                    name: 'data-display' // For potential future updates
                });
                componentGroup.add(dataDisplay);
            } else {
                dataDisplay.text(`Output ${outputName}: ${JSON.stringify(data)}`);
            }
            mainLayer.draw();
        } else {
            console.warn(`[WebSocket] Component ${componentId} not found on stage to display output.`);
        }
    }
    // Handle connection.created event from server (broadcast from another client)
    else if (parsedMessage.method === "v1.connection.created") { // Versioned
        console.log('[WebSocket] Received v1.connection.created:', parsedMessage.params);
        if (connections.has(parsedMessage.params.connectionId)) {
            console.log(`[WebSocket] Connection ${parsedMessage.params.connectionId} already exists (likely self-echo). Ignoring v1.connection.created.`);
        } else {
            // Attempt to render the connection. renderLoadedConnection handles queuing if components aren't ready.
            const success = renderLoadedConnection(parsedMessage.params);
            if (success) {
                console.log(`[WebSocket] Live connection ${parsedMessage.params.connectionId} created successfully.`);
            } else {
                console.log(`[WebSocket] Live connection ${parsedMessage.params.connectionId} queued or failed to render immediately.`);
            }
        }
    }
    // Handle connection.removed event from server (broadcast from another client)
    else if (parsedMessage.method === "v1.connection.removed") { // Versioned
        console.log('[WebSocket] Received v1.connection.removed:', parsedMessage.params);
        const connectionIdToRemove = parsedMessage.params.connectionId;
        const connEntry = connections.get(connectionIdToRemove);

        if (connEntry) {
            if (connEntry.line) {
                connEntry.line.destroy();
            }
            connections.delete(connectionIdToRemove);
            mainLayer.draw();
            console.log(`[WebSocket] Live connection ${connectionIdToRemove} removed successfully via v1.connection.removed.`);
        } else {
            console.warn(`[WebSocket] Could not find connection ${connectionIdToRemove} to remove (already removed or never existed here) via v1.connection.removed.`);
        }
    }

  } catch (error) {
    console.error('[WebSocket] Error parsing message or handling method:', error, event.data);
  }
};

function createWire({ id, fromPort, toPort }) {
  const logPrefix = `[createWire](${id}):`;
  console.log(`${logPrefix} Creating wire from ${fromPort.getParent().id()}:${fromPort.name()} to ${toPort.getParent().id()}:${toPort.name()}.`);

  const sourcePos = fromPort.getAbsolutePosition();
  const targetPos = toPort.getAbsolutePosition();

  if (!sourcePos || !targetPos) {
    console.error(`${logPrefix} Could not get absolute positions for ports. Source:`, sourcePos, "Target:", targetPos);
    return null; // Cannot create wire
  }

  const wire = new Konva.Line({
    id: id,
    points: [sourcePos.x, sourcePos.y, targetPos.x, targetPos.y],
    stroke: 'dodgerblue',
    strokeWidth: 3,
    lineCap: 'round',
    lineJoin: 'round'
    // dash: [] // Solid line for committed connections
  });

  mainLayer.add(wire);
  wire.moveToBottom(); // Ensure wires are behind components

  connections.set(id, { // Changed for Map
    id: id,
    from: fromPort,
    to: toPort,
    line: wire
  });

  wire.on('contextmenu', function(event) {
    event.evt.preventDefault();
    if (confirm('Delete this connection?')) {
      const deleteMessage = {
        jsonrpc: "2.0",
        method: "v1.connection.delete", // Versioned
        params: { connectionId: id }, // Use the id from closure
        id: 'msg_delete_' + Date.now()
      };
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(deleteMessage));
        console.log(`${logPrefix} Sent connection.delete for: ${id}`);
      } else {
        console.error(`${logPrefix} WebSocket not open. Cannot send connection.delete for ${id}`);
      }

      // connections.delete(id) is the primary Map operation.
      // The wire object (this) is already available from the event.
      if (connections.has(id)) {
          connections.delete(id);
          console.log(`${logPrefix} Connection ${id} removed from Map.`);
      } else {
          console.warn(`${logPrefix} Connection ${id} not found in Map for deletion.`);
      }
      wire.destroy(); // Destroy the line itself (wire is 'this' Konva.Line here)
      mainLayer.draw(); // Redraw after deleting and destroying
      console.log(`${logPrefix} Connection visual line ${id} deleted from frontend.`);
    }
  });

  mainLayer.draw(); // Draw the layer to show the new wire
  console.log(`${logPrefix} Wire created and stored.`);
  return wire;
}

function renderLoadedConnection(params, isRetry = false) {
  const logPrefix = `[renderLoadedConnection${isRetry ? '-retry' : ''}](${params.connectionId}):`;
  console.log(`${logPrefix} Attempting to render.`);

  const sourceComponent = mainStage.findOne('#' + params.sourceComponentId);
  const targetComponent = mainStage.findOne('#' + params.targetComponentId);

  if (!sourceComponent || !targetComponent) {
    if (!sourceComponent) console.warn(`${logPrefix} Source component ${params.sourceComponentId} not found.`);
    if (!targetComponent) console.warn(`${logPrefix} Target component ${params.targetComponentId} not found.`);

    const alreadyQueued = pendingConnections.find(p => p.connectionId === params.connectionId);
    if (!alreadyQueued) {
        console.log(`${logPrefix} Queuing connection.`);
        pendingConnections.push(JSON.parse(JSON.stringify(params))); // Store a deep copy
    } else {
        // console.log(`${logPrefix} Connection already in queue.`); // Can be noisy, uncomment if needed
    }
    return false;
  }

  // Updated source port lookup
  const sourceOutputPortNodes = sourceComponent.find(node => node.name() === params.sourcePortName && node.getClassName() === 'Circle');
  const sourceOutputPort = sourceOutputPortNodes.length > 0 ? sourceOutputPortNodes.toArray()[0] : null;

  // Updated target port lookup
  const targetInputPortNodes = targetComponent.find(node => node.name() === params.targetPortName && node.getClassName() === 'Circle');
  const targetInputPort = targetInputPortNodes.length > 0 ? targetInputPortNodes.toArray()[0] : null;

  if (!sourceOutputPort || !targetInputPort) {
    if (!sourceOutputPort) console.warn(`${logPrefix} Source port Circle named '${params.sourcePortName}' in ${params.sourceComponentId} not found.`);
    if (!targetInputPort) console.warn(`${logPrefix} Target port Circle named '${params.targetPortName}' in ${params.targetComponentId} not found.`);

    const alreadyQueued = pendingConnections.find(p => p.connectionId === params.connectionId);
    if (!alreadyQueued) {
        console.log(`${logPrefix} Queuing connection due to missing ports.`);
        pendingConnections.push(JSON.parse(JSON.stringify(params))); // Store a deep copy
    } else {
        // console.log(`${logPrefix} Connection already in queue (port issue).`);  // Can be noisy
    }
    return false;
  }

  const sourcePortPos = sourceOutputPort.getAbsolutePosition(); // Changed: No argument
  const targetPortPos = targetInputPort.getAbsolutePosition(); // Changed: No argument

  if (!sourcePortPos || !targetPortPos) {
      console.error(`${logPrefix} Could not get absolute positions for ports. Source:`, sourcePortPos, "Target:", targetPortPos);
      return false; // Don't queue, this is an unexpected error if components/ports were found
  }

  // If we're here, components and ports are found. Remove from pending if it was a retry.
  const pendingIndex = pendingConnections.findIndex(p => p.connectionId === params.connectionId);
  if (pendingIndex > -1) {
    pendingConnections.splice(pendingIndex, 1);
    console.log(`${logPrefix} Removed successfully rendered connection from pending queue.`);
  }

  // Prevent re-rendering if line already exists (e.g. from a previous attempt / race condition)
  // Check Konva state AND our map state.
  const konvaLineExists = mainStage.findOne('#' + params.connectionId);
  const mapEntryExists = connections.has(params.connectionId);

  if (konvaLineExists) {
      console.warn(`${logPrefix} Line with ID ${params.connectionId} already exists on stage.`);
      if (!mapEntryExists) {
           console.warn(`${logPrefix} Line was on stage but not in connections Map. Adding to Map now.`);
           // This implies an inconsistency; ideally, createWire should be the sole source of truth for adding to both.
           // However, to robustly handle, we can add it here.
           connections.set(params.connectionId, { // Changed for Map
                id: params.connectionId,
                from: sourceOutputPort, // These ports are already found
                to: targetInputPort,
                line: konvaLineExists // Use the existing Konva line
            });
      }
      return true; // Considered "handled" if the line is on stage.
  }
  // If map entry exists but Konva line doesn't, it's an inconsistency.
  // For now, we'll proceed to createWire which will overwrite the map entry if needed.
  if (mapEntryExists && !konvaLineExists) {
      console.warn(`${logPrefix} Connection ${params.connectionId} exists in Map but not on stage. Proceeding to recreate.`);
  }


  // Create the wire using the new helper function
  const wire = createWire({
    id: params.connectionId,
    fromPort: sourceOutputPort,
    toPort: targetInputPort
    // isInitialLoad: true // This param is not currently used by createWire but could be passed
  });

  if (wire) {
    console.log(`${logPrefix} Wire creation successful via createWire.`);
    return true; // Successfully rendered
  } else {
    console.error(`${logPrefix} Wire creation failed via createWire.`);
    // Potentially re-queue or handle error, though createWire logs its own errors.
    // For now, if createWire returns null, it means positions couldn't be found, which
    // should have been caught by earlier checks in this function.
    return false;
  }
}

function processPendingConnections() {
  let successfullyRenderedCount = 0;
  const connectionIdsToRetry = pendingConnections.map(p => p.connectionId);

  if (connectionIdsToRetry.length === 0) {
    // console.log('[processPendingConnections] No pending connections to process.'); // Can be noisy
    return;
  }

  console.log(`[processPendingConnections] Attempting to process ${connectionIdsToRetry.length} pending connection(s):`, connectionIdsToRetry);

  // Iterate over a copy of the IDs, as renderLoadedConnection might modify pendingConnections
  connectionIdsToRetry.forEach(connectionId => {
    const params = pendingConnections.find(p => p.connectionId === connectionId);
    if (params) { // Check if it wasn't already processed and removed by a previous call in this loop
      if (renderLoadedConnection(params, true)) { // Pass true for isRetry
        successfullyRenderedCount++;
        // renderLoadedConnection now handles removing from pendingConnections on success
      }
    }
  });

  if (successfullyRenderedCount > 0) {
    console.log(`[processPendingConnections] Successfully rendered ${successfullyRenderedCount} connection(s) from queue.`);
    mainLayer.draw();
  } else {
    const remaining = pendingConnections.length;
    if (remaining > 0) {
        console.log(`[processPendingConnections] No pending connections were rendered in this pass. ${remaining} still pending.`);
    } else {
        console.log('[processPendingConnections] No pending connections rendered, and queue is now empty.');
    }
  }
}

const debouncedProcessPendingConnections = debounce(processPendingConnections, 16); // ~60fps

// Initialize Konva stage for main content
var mainStage = new Konva.Stage({
  container: 'container', // id of container <div>
  width: 500, // Should match the container div's width or be dynamic
  height: 500 // Should match the container div's height or be dynamic
});

// Add a layer to the main stage
var mainLayer = new Konva.Layer();
mainStage.add(mainLayer);

// Global variables for wiring state
var isWiring = false;
var currentWire = null;
var startPort = null;
var connections = new Map(); // Changed for Map
var pendingConnections = []; // For connections whose components aren't loaded yet

// Create a simple rectangle in the main stage
var mainRect = new Konva.Rect({
  x: 50,
  y: 50,
  width: 100,
  height: 50,
  fill: 'green',
  stroke: 'black',
  strokeWidth: 4
});

// Add the rectangle to the main layer
mainLayer.add(mainRect);

// Draw the main layer
mainLayer.draw();

// Event listener for when nodes are added to the stage (or layers within it)
// This is used to trigger pending connection processing when new components are added.
mainStage.on('add', function(evt) {
    // Check if the added node is a component group and is added to mainLayer
    if (evt.target && evt.target.name() === 'component_group' && evt.target.getLayer() === mainLayer) {
        console.log('[mainStage "add" event] Component group added to mainLayer:', evt.target.id(), '. Calling debouncedProcessPendingConnections.');
        debouncedProcessPendingConnections(); // Changed to use debounced version
    }
});

// Event listener on mainStage for mouse movement
mainStage.on('mousemove', function (e) {
  if (isWiring && currentWire) {
    const pos = mainStage.getPointerPosition();
    console.log('[stage mousemove] pos:', JSON.stringify(pos));
    currentWire.points([currentWire.points()[0], currentWire.points()[1], pos.x, pos.y]);
    console.log('[stage mousemove] currentWire points updated:', JSON.stringify(currentWire.points()));
    console.log('[stage mousemove] About to draw mainLayer.');
    mainLayer.draw();
  }
});

// Event listener on mainStage for mouse up (to cancel wiring)
mainStage.on('mouseup', function (e) {
  console.log('[stage mouseup] Triggered. isWiring:', isWiring, 'target name:', e.target.name());
  // Check if the target is not an input port or if not wiring
  // The input port's mouseup event will handle successful connections.
  // This handler is for "failed" drops or clicks not starting on an output.
  if (isWiring && e.target.name() !== 'input') {
    if (currentWire) {
      console.log('[stage mouseup] Wiring cancelled on stage. Destroying currentWire.');
      currentWire.destroy(); // Remove the wire
    }

    // Add this before resetting isWiring, currentWire, startPort
    if (startPort) { // Check if startPort is defined
        const sourceComponentGroup = startPort.getParent();
        if (sourceComponentGroup) {
            sourceComponentGroup.draggable(true);
            console.log('[stage mouseup] Re-enabled dragging for source component:', sourceComponentGroup.id(), 'due to wiring cancellation.');
        }
    }

    // Reset wiring state
    isWiring = false;
    currentWire = null;
    startPort = null;
    mainLayer.draw();
  } else if (!isWiring && currentWire) {
    // This case might occur if mouseup happens on stage after a successful connection
    // or if something went wrong. Clean up currentWire if it exists.
    console.log('[stage mouseup] Cleanup: !isWiring but currentWire exists. Destroying currentWire.');
    currentWire.destroy();
    currentWire = null;
    mainLayer.draw();
  }
});

// Get the sidebar element
const sidebarDiv = document.getElementById('sidebar');

// Initialize Konva stage for sidebar
if (sidebarDiv) {
  var sidebarStage = new Konva.Stage({
    container: sidebarDiv, // Use the div element directly
    width: sidebarDiv.clientWidth, // Dynamically set width
    height: 200 // Example height, adjust as needed
  });

  // Add a layer to the sidebar stage
  var sidebarLayer = new Konva.Layer();
  sidebarStage.add(sidebarLayer);

  // Create a 'Dummy Component' rectangle for the sidebar
  const initialSidebarComponentX = 10;
  const initialSidebarComponentY = 10;
  var dummyComponent = new Konva.Rect({
    x: initialSidebarComponentX,
    y: initialSidebarComponentY,
    width: 50,
    height: 50,
    fill: 'blue',
    stroke: 'black',
    strokeWidth: 2,
    draggable: true // Make the component draggable
  });

  // Add the dummy component to the sidebar layer
  sidebarLayer.add(dummyComponent);

  // Draw the sidebar layer
  sidebarLayer.draw();

  // Event listener for when the draggable sidebar component is dropped
  dummyComponent.on('dragend', function() {
    console.log("Sidebar dummy component drag ended.");

    // Get the pointer position relative to the main stage.
    // This is where the user dropped the component.
    var pointerPosition = mainStage.getPointerPosition();

    // Reset the original sidebar component to its initial position
    dummyComponent.position({ x: initialSidebarComponentX, y: initialSidebarComponentY });
    sidebarLayer.draw(); // Redraw sidebar layer to show the component back in place
    console.log("Sidebar dummy component position reset.");

    // If pointerPosition is null, it means the drop happened outside any Konva stage,
    // or the mainStage is not present.
    if (!pointerPosition) {
        console.warn("Drop event occurred, but pointer position is not available (possibly dropped outside of any Konva area or mainStage missing).");
        return;
    }

    // Check if the drop position is within the valid bounds of the mainStage.
    // We subtract the component's dimensions from the stage dimensions for the x, y checks
    // to ensure the entire component is within the bounds, assuming x,y is top-left.
    // For this example, we'll check if the drop point (cursor) is within the stage.
    // A more robust check might ensure the entire new shape fits.
    const withinXBounds = pointerPosition.x > 0 && pointerPosition.x < mainStage.width();
    const withinYBounds = pointerPosition.y > 0 && pointerPosition.y < mainStage.height();

    if (withinXBounds && withinYBounds) {
      console.log(`Drop position (main stage relative): X=${pointerPosition.x}, Y=${pointerPosition.y} - Within bounds.`);

      // Create a Konva.Group for the component (rectangle + label)
      var componentGroup = new Konva.Group({
        x: pointerPosition.x - dummyComponent.width() / 2,
        y: pointerPosition.y - dummyComponent.height() / 2,
        draggable: true,
        id: 'comp_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9), // Assign unique ID
        name: 'component_group' // <-- Add this line
      });

      // Create the rectangle for the component (relative to the group)
      var newRect = new Konva.Rect({
        x: 0, // Position relative to the group
        y: 0, // Position relative to the group
        width: dummyComponent.width(),
        height: dummyComponent.height(),
        fill: 'red',
        stroke: 'black',
        strokeWidth: 2
        // draggable: false, // Not needed as group is draggable
      });

      // Create the label for the component (relative to the group)
      var label = new Konva.Text({
        x: 0, // Position relative to the group
        y: 0, // Position relative to the group
        text: 'Dummy Component',
        fontSize: 12,
        fontFamily: 'Arial',
        fill: 'black',
        width: dummyComponent.width(), // Match rectangle width for centering
        height: dummyComponent.height(), // Match rectangle height for centering
        align: 'center',
        verticalAlign: 'middle'
      });

      // Add rectangle and label to the group
      componentGroup.add(newRect);
      componentGroup.add(label);

      // Define port appearance
      const portRadius = 5;
      const portFill = 'gray';
      const portStroke = 'black';
      const portStrokeWidth = 1;

      // Create input port
      var inputPort = new Konva.Circle({
        x: 0, // Left edge of the newRect
        y: newRect.height() / 2, // Vertically centered
        radius: portRadius,
        fill: portFill,
        stroke: portStroke,
        strokeWidth: portStrokeWidth,
        name: 'input' // Added name property
      });
      componentGroup.add(inputPort);

      // Input port hover effects
      inputPort.on('mouseenter', function() {
        mainStage.container().style.cursor = 'pointer';
        this.fill('yellow');
        this.radius(portRadius * 1.2);
        if (isWiring && currentWire) {
          currentWire.stroke('green');
        }
        mainLayer.draw();
      });
      inputPort.on('mouseleave', function() {
        mainStage.container().style.cursor = 'default';
        this.fill(portFill);
        this.radius(portRadius);
        if (isWiring && currentWire) {
          currentWire.stroke('dodgerblue');
        }
        mainLayer.draw();
      });

      // Event listener for input port
      inputPort.on('mouseup', function(e) {
        console.log('[input mouseup] Triggered. isWiring:', isWiring, 'startPort:', startPort);
        console.log('[input mouseup] Condition check: isWiring=', isWiring, 'startPort exists=', !!startPort, 'parents different=', startPort ? startPort.getParent() !== inputPort.getParent() : 'N/A');
        if (isWiring && startPort && startPort.getParent() !== inputPort.getParent()) {
          // Successfully completed a new wire connection interactively
          console.log('[input mouseup] Successful connection attempt.');

          if (currentWire) {
            currentWire.destroy(); // Destroy the temporary dashed line
            console.log('[input mouseup] Destroyed temporary currentWire.');
          }

          const connectionId = 'conn_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
          const sourceComponentId = startPort.getParent().id();
          const targetComponentId = inputPort.getParent().id(); // 'this' is the inputPort Konva.Circle

          // Create the permanent wire using the helper function
          const newWireObject = createWire({
            id: connectionId,
            fromPort: startPort, // The output port where dragging started
            toPort: inputPort    // The input port where dragging ended
          });

          if (newWireObject) {
            console.log(`[input mouseup] Permanent wire ${connectionId} created via createWire.`);
            // Send message to backend
            const message = {
              jsonrpc: "2.0",
              method: "v1.connection.create", // Versioned
              params: {
                connectionId: connectionId,
                sourceComponentId: sourceComponentId,
                sourcePortName: startPort.name(),
                targetComponentId: targetComponentId,
                targetPortName: inputPort.name()
              },
              id: 'msg_create_' + Date.now()
            };

            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify(message));
              console.log("[input mouseup] Sent connection.create message:", message);
            } else {
              console.error("[input mouseup] WebSocket is not open. Cannot send connection.create message.");
              // Optionally, remove the wire if backend communication fails? Or queue message?
              // For now, keeping it on frontend.
            }
          } else {
            console.error(`[input mouseup] Failed to create permanent wire for ${connectionId}.`);
            // mainLayer.draw() might be needed if createWire failed early and didn't draw
          }

          // Add this before resetting isWiring, currentWire, startPort
          const sourceComponentGroup = startPort.getParent();
          if (sourceComponentGroup) {
              sourceComponentGroup.draggable(true);
              console.log('[input mouseup] Re-enabled dragging for source component:', sourceComponentGroup.id());
          }

          // Reset wiring state
          isWiring = false;
          currentWire = null;
          startPort = null;
          // mainLayer.draw() is called by createWire, so not strictly needed here unless createWire fails.
          // However, createWire calls draw, so if it fails, the temp wire is already gone.

        } else {
          console.log('[input mouseup] Failed connection or self-connection attempt.');
          if (currentWire) { // If wiring failed, destroy the temporary wire
            currentWire.destroy();
            console.log('[input mouseup] Destroyed temporary currentWire due to failed connection.');
          }

          // Add this logic:
          if (startPort) { // Check if startPort is defined (it should be if isWiring was true)
              const sourceComponentGroup = startPort.getParent();
              if (sourceComponentGroup) {
                  sourceComponentGroup.draggable(true);
                  console.log('[input mouseup][failure path] Re-enabled dragging for source component:', sourceComponentGroup.id());
              }
          }

          isWiring = false;
          currentWire = null;
          startPort = null;
          mainLayer.draw(); // Draw to remove the temp wire if nothing else changed
        }
      });

      // Create output port
      var outputPort = new Konva.Circle({
        x: newRect.width(), // Right edge of the newRect
        y: newRect.height() / 2, // Vertically centered
        radius: portRadius,
        fill: portFill,
        stroke: portStroke,
        strokeWidth: portStrokeWidth,
        name: 'output' // Added name property
      });
      componentGroup.add(outputPort);

      // Output port hover effects
      outputPort.on('mouseenter', function() {
        mainStage.container().style.cursor = 'pointer';
        this.fill('yellow');
        this.radius(portRadius * 1.2);
        mainLayer.draw();
      });
      outputPort.on('mouseleave', function() {
        mainStage.container().style.cursor = 'default';
        this.fill(portFill);
        this.radius(portRadius);
        mainLayer.draw();
      });

      // Event listener for output port
      outputPort.on('mousedown', function(e) {
        e.evt.stopPropagation(); // Prevent event bubbling to the component group
        isWiring = true;
        startPort = outputPort; // <<< EXISTING LINE

        // Add this:
        const componentGroup = startPort.getParent();
        if (componentGroup) {
            componentGroup.draggable(false);
            console.log('[output mousedown] Disabled dragging for component:', componentGroup.id());
        }
        // ... rest of the function
        const startPos = startPort.getAbsolutePosition(mainStage);
        console.log('[output mousedown] startPos:', JSON.stringify(startPos));
        currentWire = new Konva.Line({
          points: [startPos.x, startPos.y, startPos.x, startPos.y],
          stroke: 'red', // Styling for the dragged wire
          strokeWidth: 4, // Styling for the dragged wire
          lineCap: 'round',
          lineJoin: 'round',
          dash: [10, 5] // Dashed line for dragging
        });
        console.log('[output mousedown] currentWire created:', currentWire);
        mainLayer.add(currentWire);
        console.log('[output mousedown] About to draw mainLayer.');
        mainLayer.draw();
      });

      // Add the group to the main layer
      mainLayer.add(componentGroup);

      // Add dragmove event listener to the componentGroup
      componentGroup.on('dragmove', function() {
        const draggedComponent = this; // 'this' refers to componentGroup
        connections.forEach(connection => {
          // Check if the wire starts from the dragged component
          if (connection.from.getParent().id() === draggedComponent.id()) {
            const startPortAbsPos = connection.from.getAbsolutePosition(mainStage);
            connection.line.points([startPortAbsPos.x, startPortAbsPos.y, connection.line.points()[2], connection.line.points()[3]]);
          }
          // Check if the wire ends at the dragged component
          if (connection.to.getParent().id() === draggedComponent.id()) {
            const endPortAbsPos = connection.to.getAbsolutePosition(mainStage);
            connection.line.points([connection.line.points()[0], connection.line.points()[1], endPortAbsPos.x, endPortAbsPos.y]);
          }
        });
        mainLayer.draw();
      });

      mainLayer.draw(); // Ensure this is called after all additions
      console.log("New component group with ports created on main stage.");

    } else {
      console.log(`Drop position (main stage relative): X=${pointerPosition.x}, Y=${pointerPosition.y} - Outside main stage bounds.`);
    }
  });

} else {
  console.error("Sidebar element not found! Cannot initialize sidebar stage or dummy component.");
}

// Render the AIChatInterface component
const chatContainer = document.getElementById('react-chat-container');
if (chatContainer) {
  ReactDOM.render(React.createElement(AIChatInterface), chatContainer);
} else {
  console.error('Error: react-chat-container not found in the DOM.');
}