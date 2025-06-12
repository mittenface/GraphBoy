# Dual-Agent Synchronized Task Pair System

## 1. System Overview

This document describes a system for managing a shared, synchronized list of paired tasks between two autonomous agents. The system ensures that both agents work on tasks in a coordinated manner, respecting sequence and dependencies defined by task pairs. It relies on a central JSON task file, a file-based locking mechanism, and a command-line interface (CLI) for administration.

The core components are:
*   **Task File (`tasks.json`):** A JSON file serving as the central repository for task definitions and task pair configurations. It contains two main arrays: `task_pairs` and `tasks`.
*   **Lock File (`tasks.lock`):** A file used to manage exclusive access to `tasks.json`, preventing concurrent modifications and ensuring data integrity.
*   **Agents (Agent 1 & Agent 2):** Autonomous entities that read from and update `tasks.json`, performing the actual work defined by individual tasks within the pairs.
*   **Task Manager CLI (`task_manager_cli.py`):** A Python script providing command-line tools for initializing, viewing, and modifying `tasks.json`.
*   **Monitor (Conceptual):** While not implemented in the initial scripts, a future monitor could oversee system health, detect stale locks, and manage dead agents.

## 2. Setup Instructions

1.  **Initialize `tasks.json`:**
    *   Use the `task_manager_cli.py` script: `python task_manager_cli.py init`
    *   This creates `tasks.json` with the required structure: `{"task_pairs": [], "tasks": []}`.
    *   Alternatively, manually create an empty `tasks.json` with this structure.
        ```json
        {
          "task_pairs": [],
          "tasks": []
        }
        ```
2.  **Shared Directory:** Ensure both agents and any administrative user of `task_manager_cli.py` have read/write access to a common directory where `tasks.json` and `tasks.lock` will reside.
3.  **Agent Configuration:**
    *   Each agent needs a unique identifier (e.g., "Agent1", "Agent2"). This ID is used for `agent_preference` in tasks.
    *   Agents must be programmed with the logic outlined in "Agent Workflow."

## 3. Task File Format (`tasks.json`)

The `tasks.json` file is a JSON object containing two main keys: `task_pairs` and `tasks`.

```json
{
  "task_pairs": [
    {
      "pair_id": "unique_pair_id_string",
      "tasks": ["task_id_1", "task_id_2"],
      "status": "BLOCKED | READY | COMPLETED",
      "pair_lock": true,
      "sequence_index": 1
    }
    // ... more task pairs
  ],
  "tasks": [
    {
      "id": "unique_task_id_string",
      "pair_id": "unique_pair_id_string | null",
      "agent_preference": "Agent1_ID | Agent2_ID | null",
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
}
```

**`task_pairs` Array:** Each object in this array defines a pair of tasks and their collective state.
*   `pair_id`: (String) A unique identifier for the task pair (e.g., "pair_001").
*   `tasks`: (Array of Strings) An array containing exactly two task IDs that form this pair. These IDs must correspond to tasks defined in the `tasks` array.
*   `status`: (String) The current collective status of the task pair.
    *   `BLOCKED`: This pair is waiting for a preceding pair to complete and cannot be worked on.
    *   `READY`: This pair is unlocked and its constituent tasks can be picked up by agents.
    *   `COMPLETED`: Both tasks in this pair have been completed.
*   `pair_lock`: (Boolean, Optional) Indicates if the pair is administratively/procedurally locked. Typically `true` for `BLOCKED` pairs and `false` for `READY` pairs. Agents should only consider pairs where `pair_lock` is `false`. (Default: `true` if `status` is `BLOCKED`, `false` if `status` is `READY`).
*   `sequence_index`: (Integer) A numerical index determining the order in which task pairs should be processed. Lower numbers are processed first.

**`tasks` Array:** Each object describes an individual task.
*   `id`: (String) A universally unique identifier for the task (e.g., UUID or "task_A01").
*   `pair_id`: (String | null) The `pair_id` of the task pair this task belongs to. `null` if it's a standalone task (though the current system focuses on paired tasks).
*   `agent_preference`: (String | null) The preferred agent ID (e.g., "Agent1", "Agent2") to work on this task. This helps in routing tasks within a pair to specific agents.
*   `description`: (String) A clear and concise description of what needs to be done.
*   `status`: (String) The current state of the task: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`.
*   `assigned_to`: (String | null) The ID of the agent currently assigned to or working on the task.
*   `created_at`: (String) ISO 8601 timestamp of when the task was created.
*   `updated_at`: (String) ISO 8601 timestamp of when the task was last modified.
*   `history`: (Array) An array of event objects logging significant lifecycle events for this task.

## 4. Agent Workflow

Agents interact with `tasks.json` under the protection of `tasks.lock`.

1.  **Acquire Lock:** Attempt to acquire `tasks.lock`. If unavailable, wait and retry.
2.  **Read Data:** Once lock is acquired, read the entire content of `tasks.json` (both `task_pairs` and `tasks`).
3.  **Identify Actionable Task:**
    a.  Sort `task_pairs` by `sequence_index` in ascending order.
    b.  Iterate through sorted pairs to find the first `task_pair` where `status` is `READY` and `pair_lock` is `false` (or not explicitly `true`). This is the "active pair."
    c.  If no active pair is found, release lock and wait before retrying.
    d.  Within the active pair, iterate through its referenced task IDs (from `task_pairs[n].tasks`). For each task ID, find the corresponding task object in the main `tasks` array.
    e.  The agent should look for a task that:
        i.  Matches its `agent_preference`.
        ii. Is in `PENDING` status.
        iii. (Optional) If `agent_preference` is not set or doesn't match, an agent could pick any `PENDING` task within the active pair that isn't already assigned, ensuring tasks from the same pair are ideally picked by different agents.
    f.  If its preferred task is already `IN_PROGRESS` by itself, it can continue. If `IN_PROGRESS` by another agent, it should not interfere.

4.  **Claim and Process Task:**
    a.  If a suitable `PENDING` task is found, the agent updates the task's `status` to `IN_PROGRESS`, sets `assigned_to` to its own ID, and updates `updated_at`. A history event is logged.
    b.  Write changes to `tasks.json`.
    c.  Release `tasks.lock`.
    d.  Perform the actual work associated with the task. This happens *after* releasing the lock.

5.  **Post-Work Update (Task Completion/Failure):**
    a.  Re-acquire `tasks.lock`.
    b.  Read `tasks.json` again.
    c.  Update the processed task's `status` to `COMPLETED` (or `FAILED`), update `updated_at`, and log a history event.
    d.  **Pair Completion Check:**
        i.  Retrieve the `pair_id` from the completed task.
        ii. Check the status of all tasks belonging to this `pair_id`.
        iii. If all tasks in the pair are `COMPLETED`:
            1.  Find the corresponding `task_pair` object.
            2.  Change its `status` to `COMPLETED`.
            3.  Set `pair_lock: true` (optional, but good practice for completed pairs).
            4.  **Advance Next Pair:** Find the *next* `task_pair` in sequence (the one with the lowest `sequence_index` greater than the just-completed pair's index). If this next pair has a `status` of `BLOCKED`, change its `status` to `READY` and set `pair_lock: false`. This "unlocks" the next pair for processing.
    e.  Write all changes to `tasks.json`.
    f.  Release `tasks.lock`.

## 5. Synchronization Rules

*   **Mandatory Locking for `tasks.json`:** All reads and writes to `tasks.json` MUST occur only after acquiring `tasks.lock`.
*   **Atomic Operations:** The sequence of acquiring lock, reading data, modifying data, writing data, and releasing lock should be as short and efficient as possible.
*   **Pair Advancement:**
    *   A `task_pair` transitions from `BLOCKED` to `READY` only when the preceding `task_pair` (by `sequence_index`) is `COMPLETED`. This is typically done by the agent that completes the last task of the preceding pair.
    *   The `advance_next_pair` command in `task_manager_cli.py` can also be used for manual advancement if needed.
*   **Agent Task Specialization (Guideline):** Tasks within a pair should ideally be handled by different agents, as guided by the `agent_preference` field for each task. This promotes parallelism. Agents should prioritize tasks matching their preference within an active, unlocked pair.
*   **`task_pair` Status Updates:** Any changes to a `task_pair` object (e.g., status, `pair_lock`) require holding `tasks.lock`.
*   **Lock File Content:** `tasks.lock` should store the ID of the locking agent and a timestamp to help identify stale locks. Example: `{"agent_id": "Agent1", "timestamp": "..."}`.
*   **Stale Lock Resolution:** Stale locks (locks held for an excessive duration) may indicate a crashed agent. Manual removal or a monitor process is needed. Agents may incorporate a timeout for breaking stale locks, but this must be implemented carefully.

## 6. Running the Monitor (Conceptual)

(Content remains largely the same as previous version - focused on stale lock detection, dead agent detection, integrity checks, logging.)

## 7. Tips for Management

(Content remains largely the same - focus on unique IDs, timestamps, error handling, backups, clear descriptions, idempotency, incremental rollout, logging, stale lock timeout, manual lock removal.)
*   **Sequential `sequence_index`:** Ensure `sequence_index` for `task_pairs` are unique and correctly ordered. Gaps are acceptable but direct sequence is easier to manage.

## 8. Helper Script: `task_manager_cli.py`

`task_manager_cli.py` is a command-line utility for manual administration and inspection of the `tasks.json` file. It helps in setting up the initial file, adding tasks and pairs, checking status, and manually advancing task pairs if necessary. All operations that modify `tasks.json` performed by the CLI acquire and release `tasks.lock`.

**Key Commands:**

*   **`init [--force]`**:
    *   Initializes `tasks.json` with `{"task_pairs": [], "tasks": []}`.
    *   `--force`: Overwrites `tasks.json` if it already exists.
*   **`add_task --desc <description> [--agent_pref <agent_id>] [--pair_id <pair_id>] [--task_id <task_id>]`**:
    *   Adds a new task to the `tasks` array.
    *   `--desc`: Task description (required).
    *   `--agent_pref`: Preferred agent ID for this task.
    *   `--pair_id`: Assigns this task to an existing task pair.
    *   `--task_id`: Specify a custom task ID (default is UUID).
*   **`add_pair --task_id1 <task_id1> --task_id2 <task_id2> --seq_idx <index> [--pair_id <pair_id>] [--status <status>] [--lock <true|false>]`**:
    *   Creates a new task pair in the `task_pairs` array.
    *   `--task_id1`, `--task_id2`: IDs of the two tasks forming the pair (must exist).
    *   `--seq_idx`: Sequence index for the pair (required).
    *   `--pair_id`: Specify a custom pair ID (default is "pair_" + UUID).
    *   `--status`: Initial status (e.g., "BLOCKED", "READY", default "BLOCKED").
    *   `--lock`: Initial lock state (`true` or `false`). Defaults based on status.
*   **`create_full_pair --desc1 <desc1> --agent1 <agent1_id> --desc2 <desc2> --agent2 <agent2_id> --seq_idx <index> [--pair_id <pair_id_prefix>]`**:
    *   A convenience command that creates two new tasks and a new pair linking them.
    *   `--desc1`, `--agent1`: Description and preferred agent for the first task.
    *   `--desc2`, `--agent2`: Description and preferred agent for the second task.
    *   `--seq_idx`: Sequence index for the new pair.
    *   `--pair_id`: Optional custom prefix for the generated pair ID and task IDs.
*   **`status [--pair_id <pair_id>] [--task_id <task_id>]`**:
    *   Displays the status of specific tasks or pairs, or all if no ID is provided.
    *   If `pair_id` is given, shows the pair and its constituent tasks.
    *   If `task_id` is given, shows the specific task.
*   **`advance_next_pair [--force]`**:
    *   Finds the current highest `COMPLETED` pair by `sequence_index`.
    *   Then finds the next pair in sequence. If that pair is `BLOCKED`, changes its status to `READY` and `pair_lock` to `false`.
    *   `--force`: Allows advancing even if the "current" completed pair isn't found (e.g., for initial setup or recovery). Useful to kickstart the first `BLOCKED` pair to `READY`.
*   **`validate`**:
    *   Performs integrity checks on `tasks.json`:
        *   Checks for duplicate task IDs or pair IDs.
        *   Ensures task IDs in pairs exist in the `tasks` list.
        *   Verifies `sequence_index` uniqueness for pairs.
        *   Checks for orphaned tasks (tasks with a `pair_id` that doesn't exist).

This CLI script is essential for managing the lifecycle of tasks and pairs, especially for bootstrapping the system or recovering from unexpected states.
```
