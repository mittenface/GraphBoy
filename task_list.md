# Comprehensive Task List for Dual Agent Setup

This document outlines the development tasks for building the Modular Canvas Application, broken down for a dual-agent workflow. Tasks are paired to be complementary and, where possible, allow for simultaneous work. Refer to `design_document.md` for detailed specifications.

## Agent 1 Tasks (Primarily Frontend & UX)

### Phase 1: Canvas + Dummy Component (MVP 0.1)
- [ ] Set up the basic HTML structure for the application.
- [ ] Initialize a canvas library (e.g., Konva.js or Fabric.js) within the frontend framework.
- [ ] Implement a component library menu/sidebar with a draggable "Dummy Component" item.
- [ ] Enable dragging the "Dummy Component" from the menu and dropping it onto the canvas.
- [ ] Render a simple visual representation (e.g., a rectangle with a label "Dummy Component") on the canvas at the drop position.
- [ ] Ensure the dummy component has visual placeholders for ports (non-functional).

### Phase 2: Functional Chat Component (MVP 0.2)
- [ ] Develop the React component for the "AI Chat Interface" (visuals, input fields for `userInput`, `temperature`, `maxTokens`).
- [ ] Implement frontend logic to capture values from chat input fields.
- [ ] Trigger a request to the backend when `userInput` is submitted.
- [ ] Display `responseText` received from the backend in the chat component.
- [ ] Visually indicate `responseStream` activity from the backend.
- [ ] Display any `error` messages or status from the backend in the chat component.
- [ ] Render the chat component's visual ports (`userInput`, `temperature`, `maxTokens` as inputs; `responseText`, `responseStream`, `error` as outputs) according to its manifest.

### Phase 3: Port Wiring & Data Flow (MVP 0.3)
- [ ] Implement UI interactions for port wiring on the canvas (click-and-drag from output to input).
- [ ] Provide visual feedback during the wire drag operation.
- [ ] Validate basic connection attempts (e.g., text-to-text, prevent output-to-output).
- [ ] Render visual connections (wires) between components on the canvas.
- [ ] Update frontend centralized state to maintain a `connections` list.
- [ ] Communicate connection changes (creations, deletions) to the backend/event bus.
- [ ] Implement UI for deleting connections.
- [ ] Develop the frontend for the "Text Display" component (to show text from a wired component).

### Phase 4: Second Component & Numeric Nodes (MVP 0.4)
- [ ] Develop the frontend for a "Number Input" component (or "Slider") with a numeric output port.
- [ ] Develop the frontend for a "Value Display" component (or modify an existing component for numeric input).
- [ ] Ensure ports of type `number` are visually distinct from `text` ports.
- [ ] Extend wiring UI logic to validate and allow `number` to `number` connections.
- [ ] Prevent incompatible type connections in the UI (e.g., `text` to `number`).

### Phase 5: Streaming & Media Nodes (MVP 0.5 - Conceptual & UI)
- [ ] Design and implement UI representations for ports of type `stream`, `audio`, and `image`.
- [ ] For `stream` ports (like on Chat component), implement visual indication of active data flow.
- [ ] Conceptualize UI for displaying actual streaming text if a stream output is directly viewed (e.g., debug view).
- [ ] Design placeholder UIs for `audio` (e.g., player icon) and `image` (e.g., preview icon) components/ports.
- [ ] Consider user interactions for media components (e.g., play button for audio, preview for image).
- [ ] Ensure wiring UX can accommodate these new media types with visual consistency.

### Phase 6: Plugin System & Versioning (MVP 1.0 - UI & Feedback)
- [ ] Design UI for how newly discovered components are displayed in the component library menu.
- [ ] Design a UI section for viewing installed/available components and their versions.
- [ ] Conceptualize how errors during component loading (e.g., version mismatch, invalid manifest) are communicated to the user.
- [ ] Design how component versioning information from `manifest.json` is displayed (e.g., tooltips, info panel).
- [ ] Conceptualize UI for any developer-only flags related to the plugin system if they impact frontend.

## Agent 2 Tasks (Primarily Backend & Core Logic)

### Phase 1: Canvas + Dummy Component (MVP 0.1)
- [ ] Set up the overall project directory structure (`/frontend`, `/backend`, `/components`, `/shared_types`).
- [ ] Define the initial `manifest.json` structure (fields: `name`, `version`, `description`, basic `nodes`).
- [ ] Create a `manifest.json` file for the "Dummy Component".
- [ ] Implement a basic Component Registry & Loader to discover and parse the dummy component's manifest.
- [ ] Make the list of available components (initially just Dummy) accessible (e.g., via API or initial state).

### Phase 2: Functional Chat Component (MVP 0.2)
- [ ] Create `manifest.json` for the "AI Chat Interface" component (inputs: `userInput`, `temperature`, `maxTokens`; outputs: `responseText`, `responseStream`, `error`).
- [ ] Implement the backend module for the Chat Interface component.
- [ ] Implement `create(config)` and `update(inputs)` lifecycle methods for the chat component.
- [ ] Inside `update`, integrate with a mock LLM API for `userInput` processing.
- [ ] Implement `emit(outputName, value)` to send data to `responseText`, `responseStream`, and `error` outputs.
- [ ] Set up basic WebSocket communication (JSON-RPC) for frontend-backend interaction for this component.
- [ ] Define JSON-RPC methods for `component.updateInput` and `component.emitOutput`.
- [ ] Ensure Component Engine routes `component.updateInput` to the chat component's `update` method.
- [ ] Ensure chat component's `emit` calls translate to `component.emitOutput` WebSocket messages.

### Phase 3: Port Wiring & Data Flow (MVP 0.3)
- [ ] Implement an in-memory Event Bus for component-to-component communication.
- [ ] Develop logic to receive connection information (creations, deletions) from the frontend.
- [ ] Update backend's representation of the component graph and connections.
- [ ] Configure Event Bus subscriptions based on established connections.
- [ ] Modify "AI Chat Interface" backend to correctly publish `responseText` to the Event Bus.
- [ ] Create backend for a "Text Display" component (`manifest.json` with `inputText`; `update` method to log/store text).
- [ ] Ensure data flows from Chat component's `responseText` to Text Display's `inputText` when wired.

### Phase 4: Second Component & Numeric Nodes (MVP 0.4)
- [ ] Define `manifest.json` for new "Number Input" and "Value Display" components (or modified existing ones).
- [ ] Specify `type: "number"` for relevant input/output nodes, including `min`, `max`, `default` where applicable.
- [ ] Implement backend logic for "Number Input" (e.g., emit numeric value on change) and "Value Display" (process/store numeric input).
- [ ] Extend Event Bus and connection routing logic to robustly handle `number` type data.
- [ ] Strengthen type safety in backend connection and data routing logic, using manifest type info.
- [ ] Test end-to-end numeric data flow.

### Phase 5: Streaming & Media Nodes (MVP 0.5 - Backend Foundations)
- [ ] Define `manifest.json` examples for components with `stream`, `audio`, `image` nodes. Clarify data format (URL vs. binary).
- [ ] Refine backend for Chat component's `responseStream` for efficient text token streaming over WebSockets.
- [ ] Research and outline backend strategies for handling large binary data streams (audio/image), considering chunking, URL references, or Web Worker offloading.
- [ ] Design how Component Engine and Event Bus manage lifecycle for stream-based components (open, close, end).
- [ ] Design `rateLimit` property handling for stream outputs as per `manifest.json` (Risk Mitigation 11.2).

### Phase 6: Plugin System & Versioning (MVP 1.0 - Core Implementation)
- [ ] Implement dynamic discovery of component modules from a `/components` folder by the Component Registry & Loader.
- [ ] Implement robust `manifest.json` validation (required fields, data types, semantic versioning).
- [ ] Log errors clearly for invalid manifests or component load failures.
- [ ] Conceptualize and design sandboxing for backend modules (research VM modules, child processes, etc.).
- [ ] Design a "dry-run validator" for manifests (simulates registration without full logic execution).
- [ ] Define how component lifecycle methods from dynamically loaded backend modules are invoked.
- [ ] Establish policy for version conflict handling during component loading.
```
