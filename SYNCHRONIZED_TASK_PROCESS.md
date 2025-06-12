# Dual-Agent Synchronized Task List System

## 1. System Overview

This document describes a system for managing a shared task list between two autonomous agents. The system ensures that both agents are working from the most up-to-date task list and prevents conflicting modifications. It relies on a central task file, a locking mechanism, and a monitoring process (conceptual) to achieve synchronization.

The core components are:
*   **Task File (`tasks.json`):** A JSON file storing the list of tasks. Each task has a unique ID, description, status, assigned agent (optional), and timestamps.
*   **Lock File (`tasks.lock`):** A file used to manage exclusive access to `tasks.json`. An agent must acquire the lock before modifying the task file.
*   **Agents (Agent 1 & Agent 2):** Autonomous entities that process tasks from the `tasks.json` file.
*   **Monitor (Conceptual):** A background process responsible for overseeing the system, detecting stale locks, and potentially resolving conflicts (though the primary conflict resolution is via the lock).

## 2. Setup Instructions

1.  **Initialize `tasks.json`:**
    *   Create a file named `tasks.json` in the shared working directory.
    *   The file should contain an empty JSON array `[]` or a predefined list of tasks adhering to the format specified in "Task File Format."
    *   Example of an empty `tasks.json`:
        ```json
        []
        ```
2.  **Shared Directory:** Ensure both agents have access to a common directory where `tasks.json` and `tasks.lock` will reside.
3.  **Agent Configuration:**
    *   Each agent needs a unique identifier (e.g., "Agent1", "Agent2").
    *   Agents should be programmed with the logic to:
        *   Read and parse `tasks.json`.
        *   Acquire and release locks using `tasks.lock`.
        *   Understand task statuses and transitions.
        *   Update tasks according to the defined workflow.

## 3. Task File Format (`tasks.json`)

The `tasks.json` file is an array of task objects. Each task object has the following structure:

```json
[
  {
    "id": "unique_task_id_string",
    "description": "Detailed description of the task",
    "status": "PENDING | IN_PROGRESS | COMPLETED | FAILED",
    "assigned_to": "Agent1_ID | Agent2_ID | null",
    "created_at": "ISO8601_timestamp",
    "updated_at": "ISO8601_timestamp",
    "history": [
      {
        "timestamp": "ISO8601_timestamp",
        "event": "CREATED | ASSIGNED | STATUS_CHANGED | UPDATED",
        "agent_id": "Agent_ID_responsible_for_event | null",
        "details": "Additional information about the event"
      }
    ]
  }
  // ... more tasks
]
```

**Fields:**

*   `id`: (String) A universally unique identifier for the task (e.g., UUID).
*   `description`: (String) A clear and concise description of what needs to be done.
*   `status`: (String) The current state of the task. Allowed values:
    *   `PENDING`: Task is new and waiting to be picked up.
    *   `IN_PROGRESS`: Task is actively being worked on.
    *   `COMPLETED`: Task has been successfully finished.
    *   `FAILED`: Task could not be completed.
*   `assigned_to`: (String | null) The ID of the agent currently assigned to the task. `null` if unassigned.
*   `created_at`: (String) ISO 8601 timestamp of when the task was created.
*   `updated_at`: (String) ISO 8601 timestamp of when the task was last modified.
*   `history`: (Array) An array of objects logging significant events in the task's lifecycle.
    *   `timestamp`: ISO 8601 timestamp of the event.
    *   `event`: Type of event (e.g., `CREATED`, `ASSIGNED`, `STATUS_CHANGED`).
    *   `agent_id`: ID of the agent that triggered the event, if applicable.
    *   `details`: A brief note about the event (e.g., "Status changed from PENDING to IN_PROGRESS").

## 4. Agent Workflow

Agents should follow this general workflow:

1.  **Check for Lock:**
    *   Attempt to acquire the lock by checking for the existence of `tasks.lock`.
    *   If `tasks.lock` exists, wait for a short, random interval and retry (or implement a more sophisticated backoff strategy).
    *   If `tasks.lock` contains a timestamp, check if it's stale (older than a predefined timeout). If stale, an agent (or the monitor) might decide to break the lock (this requires careful implementation to avoid race conditions). For simplicity, agents might just wait.

2.  **Acquire Lock:**
    *   If the lock can be acquired (i.e., `tasks.lock` does not exist), create `tasks.lock`.
    *   Write the agent's ID and the current timestamp into `tasks.lock` (e.g., `{"agent_id": "Agent1", "timestamp": "2023-10-27T10:00:00Z"}`). This helps in identifying who holds the lock and when it was acquired.

3.  **Read Tasks:**
    *   Read the content of `tasks.json`.
    *   Parse the JSON data.

4.  **Process Tasks:**
    *   **Identify Assignable Tasks:** Look for tasks with `status: "PENDING"` or tasks that are `IN_PROGRESS` but assigned to *itself* (e.g., to continue work). An agent generally should not pick up a task already `IN_PROGRESS` by another agent unless a specific reassignment logic is in place.
    *   **Select a Task:** Choose a task based on priority, oldest first, or other scheduling logic.
    *   **Update Task Status:**
        *   If taking a `PENDING` task, change its `status` to `IN_PROGRESS` and set `assigned_to` to its own ID.
        *   Update `updated_at` timestamp.
        *   Add an entry to the `history` log.
    *   **Perform Work:** Execute the actions required to complete the task.
    *   **Update Task on Completion/Failure:**
        *   Change `status` to `COMPLETED` or `FAILED`.
        *   Update `updated_at` timestamp.
        *   Add an entry to the `history` log.
        *   Optionally, set `assigned_to` to `null` if the task is `COMPLETED` or `FAILED`.

5.  **Write Tasks:**
    *   Serialize the modified task list back to JSON.
    *   Overwrite `tasks.json` with the new content.

6.  **Release Lock:**
    *   Delete `tasks.lock`.

## 5. Synchronization Rules

*   **Locking is Mandatory:** No agent should read or write `tasks.json` without holding the lock.
*   **Atomic Operations:** The sequence of acquiring a lock, reading, modifying, and writing `tasks.json`, and then releasing the lock should be treated as an atomic operation as much as possible.
*   **Short Lock Duration:** Agents should hold the lock for the shortest possible time to minimize contention. Perform time-consuming task execution *after* releasing the lock if the task involves external actions and only re-acquire the lock for status updates. However, for internal state changes like assigning a task, it's often done while holding the lock.
*   **Lock File Content:** The `tasks.lock` file should contain the ID of the agent holding the lock and a timestamp. This aids in debugging and potentially in manual intervention or automated stale lock detection.
    *   Example `tasks.lock` content: `{"agent_id": "Agent1", "timestamp": "2023-10-27T10:00:00Z"}`
*   **Stale Lock Detection (Conceptual - primarily Monitor's role):**
    *   If `tasks.lock` exists for an unusually long time (beyond a defined threshold), it might indicate a crashed agent.
    *   The Monitor (or a designated agent with caution) could be responsible for identifying and potentially removing stale locks. This is a critical operation and must be handled carefully to prevent data corruption. Manual intervention is safer initially.
*   **Conflict Resolution:** The primary conflict resolution mechanism is the lock. If an agent cannot acquire the lock, it must wait and retry. "Last write wins" is the effective strategy for the `tasks.json` file itself, ensured by the locking mechanism. Content-level conflicts within the JSON (e.g., two agents trying to modify the *same field* of the *same task* in incompatible ways) are prevented if agents only modify tasks they are assigned to or are picking from `PENDING`.

## 6. Running the Monitor (Conceptual)

The Monitor is a conceptual component that would run as a separate process. Its primary responsibilities would include:

*   **Stale Lock Detection:**
    *   Periodically check `tasks.lock`.
    *   If the lock's timestamp is older than a predefined threshold (e.g., 15 minutes), flag it as potentially stale.
    *   Alert administrators or attempt an automated (but cautious) recovery, such as verifying if the owning agent process is still active before removing the lock.
*   **Dead Agent Detection:** (More advanced)
    *   If agents report heartbeats, the monitor can detect non-responsive agents.
    *   If an agent holding a lock is detected as dead, the monitor might (again, cautiously) release the lock and potentially re-queue `IN_PROGRESS` tasks assigned to that agent.
*   **Task List Integrity Checks:**
    *   Periodically scan `tasks.json` for malformed entries or inconsistencies (though the strict workflow should minimize this).
*   **Logging and Reporting:** Provide overall system health visibility.

**Note:** Implementing a robust Monitor is a significant task. Initially, manual monitoring and intervention might be necessary.

## 7. Tips for Management

*   **Unique Agent IDs:** Ensure each agent has a clearly distinct ID used in `assigned_to` fields and lock files.
*   **Timestamp Precision:** Use ISO 8601 timestamps with sufficient precision, preferably UTC, to avoid time zone issues.
*   **Error Handling:** Agents must have robust error handling, especially around file I/O and JSON parsing. If an agent crashes while holding the lock, manual intervention will be needed to remove `tasks.lock`.
*   **Backup `tasks.json`:** Regularly back up `tasks.json` to prevent data loss in case of catastrophic failure.
*   **Clear Task Descriptions:** Well-defined tasks reduce ambiguity and the chance of agents working at cross-purposes.
*   **Idempotency:** Design task operations to be idempotent where possible. If an agent attempts to re-run a completed step, it shouldn't cause negative side effects.
*   **Incremental Rollout:** Test the system thoroughly with simple tasks before deploying it for critical operations.
*   **Logging:** Agents should maintain detailed local logs of their activities, including attempts to acquire locks, tasks processed, and any errors encountered. This is invaluable for debugging.
*   **Define Stale Lock Timeout:** Establish a clear timeout period for what constitutes a "stale" lock, appropriate for the typical task processing time.
*   **Manual Lock Removal Procedure:** Have a defined, cautious procedure for manually removing `tasks.lock` if an agent crashes and leaves it behind. This should involve verifying the agent is truly inactive.
```
