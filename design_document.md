# Modular Canvas Application Design Document

## 1. Project Vision & Goals

**Core Concept:** A canvas-driven system of modular components that can be composed, wired, and extended incrementally to build interactive applications.

**Key Principles:**

* **Modularity:** Each component encapsulates its own logic, I/O nodes, and configuration schema.
* **Scalability:** Unlimited instances and dynamic I/O expansion.
* **Usability:** Intuitive drag‑and‑drop canvas, clear wiring, and real‑time parameter control.
* **Extensibility:** Easy addition of new component types (text, audio, image, streams).
* **Maintainability:** Phased development, consistent architecture, and testing baked in.

## 2. High-Level Architecture

```mermaid
flowchart LR
  subgraph Frontend
    MENU[Component Library Menu]
    CANVAS[Canvas (Konva.js or Fabric.js)]
    CONFIG[Config Panel]
  end

  subgraph Communication Layer
    BUS[Event Bus / WebSocket Gateway]
  end

  subgraph Backend
    LOADER[Component Registry & Loader]
    ENGINE[Component Engine]
    MODULES[Component Modules]
  end

  MENU -->|drag & drop| CANVAS
  CANVAS -->|user actions| BUS
  BUS <--> LOADER
  LOADER --> MODULES
  MODULES --> ENGINE
  ENGINE --> BUS
  BUS --> CANVAS
  CANVAS --> CONFIG
```

* **Frontend:** React (or Vue/Svelte) + canvas library + centralized state (Zustand/Redux).
* **Communication Layer:** JSON-RPC over WebSocket for streaming and events; in-memory event emitter for co-located components.
* **Backend:** Node.js/TypeScript (or Python/FastAPI) that dynamically discovers and loads component modules from a `/components` folder.

## 3. Component Framework

### 3.1. Definition & Manifest

Each component package includes:

1. **`manifest.json`:**

   ```json
   {
     "name": "chat-interface",
     "version": "1.0.0",
     "description": "AI chat panel",
     "nodes": {
       "inputs": [
         {"name":"userInput","type":"text"},
         {"name":"temperature","type":"number","min":0,"max":1,"default":0.7},
         {"name":"maxTokens","type":"number","min":1,"max":2048,"default":256}
       ],
       "outputs": [
         {"name":"responseText","type":"text"},
         {"name":"responseStream","type":"stream"},
         {"name":"error","type":"boolean"}
       ]
     }
   }
   ```
2. **Frontend module:** React component rendering shape, ports, and config UI.
3. **Backend module (optional):** implements lifecycle hooks and I/O processing.

### 3.2. Lifecycle Methods

* **create(config):** initialize state
* **mount(canvasContext):** render hooks
* **update(inputs):** handle new input values or triggers
* **emit(output):** push data onto bus
* **destroy():** cleanup

### 3.3. I/O Nodes & Type System

Supported types: `text`, `number`, `boolean`, `stream`, `audio`, `image`, `json`.

* **Input Node Schema:** name, type, optional min/max/default
* **Connections:** type-safe; numeric→numeric, stream→stream, etc.

## 4. Communication Protocol

| Layer                 | Protocol                       | Use Case                              |
| --------------------- | ------------------------------ | ------------------------------------- |
| Frontend ↔ Backend    | WebSocket + JSON-RPC           | Streaming tokens, parameter updates   |
| Component ↔ Component | In-memory Event Bus (pub/sub)  | Local wiring without network overhead |
| Persistence           | REST endpoints or localStorage | Saving/loading canvas state           |

**JSON-RPC Message Examples:**

```json
{ "jsonrpc":"2.0","method":"input","params":{"componentId":"c1","node":"userInput","value":"Hello"} }
{ "jsonrpc":"2.0","method":"output","params":{"componentId":"c1","node":"responseText","value":"Hi there!"} }
```

## 5. Frontend Canvas & UX

1. **Menu Sidebar:** list of component types; drag → drop to canvas.
2. **Canvas Interaction:**

   * **Select & Move:** drag shapes around.
   * **Wire Ports:** click-and-drag from port to port creates connection.
   * **Config Panel:** click component to open props and node settings.
3. **State Management:**

   * `components`: list of instances with ID, type, position, config.
   * `connections`: list of `{from:{id,node},to:{id,node}}`.
4. **Visual Aids:**

   * Port colors/icons by type.
   * Live highlights for active wires.
   * Snap-to-grid toggles.

## 6. Example: AI Chat Interface Component

* **Visual:** Rounded rectangle; top ports for modulation, side ports for text I/O.
* **Inputs:**

  * `userInput` (text — trigger)
  * `temperature`, `maxTokens` (number — modulation)
* **Outputs:**

  * `responseText` (text)
  * `responseStream` (stream)
  * `error` (boolean)
* **Behavior:**

  1. On `userInput`, call LLM API (streaming).
  2. Emit partial tokens on `responseStream`.
  3. On completion, emit full `responseText`.

## 7. Development Roadmap

| Phase | Deliverable                                | Key Focus                                  |
| ----- | ------------------------------------------ | ------------------------------------------ |
| 1     | Canvas + Dummy Component (MVP 0.1)         | Drag/drop, non‑functional ports            |
| 2     | Functional Chat Component (MVP 0.2)        | API integration, UI inputs                 |
| 3     | Port Wiring & Data Flow (MVP 0.3)          | Text transfer between two components       |
| 4     | Second Component & Numeric Nodes (MVP 0.4) | Number-type wiring, new component example  |
| 5     | Streaming & Media Nodes (MVP 0.5)          | Stream, audio, image support               |
| 6     | Plugin System & Versioning (MVP 1.0)       | Dynamic discovery, semantic version checks |

## 8. Testing & Debugging Strategy

* **Unit Tests:** Jest (backend modules), React Testing Library (frontend).
* **Integration Tests:** Simulate JSON-RPC flows end-to-end.
* **Manual QA:** Verify canvas UX, wiring, and component behaviors.
* **Logging & Tracing:**

  * Centralized event logs in dev console.
  * Error boundaries in React.

## 9. Key Technical Decisions & Challenges

1. **Frontend Framework:** React vs. Vue vs. Svelte (evaluate team skill).
2. **Backend Language:** Node.js/TypeScript vs. Python/FastAPI.
3. **Canvas Library:** Konva.js vs. Fabric.js (performance with many nodes).
4. **Communication:** WebSocket vs. local pub/sub for different layers.
5. **Module Loading & Versioning:** Semantic versioning + hot‑reload support.
6. **Security:** Sandbox backend modules; validate manifests.

## 10. Future Extensions

* **Parameter Modulation:** LFO-style auto-modulators and envelopes.
* **Groups & Macros:** Bundled sub‑circuits as higher‑order components.
* **Persistence & Collaboration:** Save to cloud; multi-user editing.
* **Marketplace:** Shareable component registry.

---

*Document will evolve as the project advances.*
