import json
import os
import time
import uuid
from datetime import datetime, timezone

TASK_FILE = "tasks.json"
LOCK_FILE = "tasks.lock"
LOCK_STALE_TIMEOUT = 300  # 5 minutes

class TaskManager:
    def __init__(self, agent_id):
        self.agent_id = agent_id

    def _log(self, message):
        """Basic logging for agent actions."""
        print(f"{datetime.now(timezone.utc).isoformat()} [{self.agent_id}]: {message}")

    def acquire_lock(self, max_wait_time=60, retry_interval=5):
        """
        Attempts to acquire the lock file.
        Returns True if lock is acquired, False otherwise.
        """
        start_time = time.time()
        while (time.time() - start_time) < max_wait_time:
            if not os.path.exists(LOCK_FILE):
                try:
                    with open(LOCK_FILE, "w") as f:
                        json.dump({"agent_id": self.agent_id, "timestamp": datetime.now(timezone.utc).isoformat()}, f)
                    self._log("Lock acquired.")
                    return True
                except IOError as e:
                    self._log(f"Error acquiring lock: {e}. Retrying...")
            else:
                # Check if the lock is stale
                try:
                    with open(LOCK_FILE, "r") as f:
                        lock_data = json.load(f)
                    lock_time = datetime.fromisoformat(lock_data.get("timestamp", ""))
                    if (datetime.now(timezone.utc) - lock_time).total_seconds() > LOCK_STALE_TIMEOUT:
                        self._log(f"Found stale lock from {lock_data.get('agent_id')}. Attempting to break it.")
                        # Break the stale lock
                        os.remove(LOCK_FILE)
                        self._log("Stale lock removed. Attempting to acquire again.")
                        # Try to acquire immediately after breaking
                        continue
                except (IOError, json.JSONDecodeError, ValueError) as e: # Added ValueError for fromisoformat
                    self._log(f"Error checking lock file, potentially corrupted: {e}. Assuming lock is held or invalid.")

                self._log(f"Lock file {LOCK_FILE} exists. Waiting...")
            time.sleep(retry_interval)

        self._log("Failed to acquire lock within the maximum wait time.")
        return False

    def release_lock(self):
        """Releases the lock file."""
        if os.path.exists(LOCK_FILE):
            try:
                # Verify lock ownership before releasing (optional but good practice)
                with open(LOCK_FILE, "r") as f:
                    lock_data = json.load(f)
                if lock_data.get("agent_id") == self.agent_id:
                    os.remove(LOCK_FILE)
                    self._log("Lock released.")
                else:
                    self._log(f"Warning: Attempted to release lock held by {lock_data.get('agent_id')}. Lock not released.")
            except (IOError, json.JSONDecodeError) as e: # Added json.JSONDecodeError
                self._log(f"Error releasing lock: {e}. Manual check might be needed.")
        else:
            self._log("No lock file to release.")

    def read_tasks(self):
        """Reads tasks from the TASK_FILE. Returns an empty list if file doesn't exist or is invalid."""
        if not os.path.exists(TASK_FILE):
            self._log(f"{TASK_FILE} not found. Returning empty list.")
            return []
        try:
            with open(TASK_FILE, "r") as f:
                tasks = json.load(f)
            return tasks
        except (IOError, json.JSONDecodeError) as e:
            self._log(f"Error reading or parsing {TASK_FILE}: {e}. Returning empty list.")
            return []

    def write_tasks(self, tasks):
        """Writes tasks to the TASK_FILE."""
        try:
            with open(TASK_FILE, "w") as f:
                json.dump(tasks, f, indent=2)
            self._log(f"Tasks successfully written to {TASK_FILE}.")
        except IOError as e:
            self._log(f"Error writing tasks to {TASK_FILE}: {e}")

    def _add_history_event(self, task, event_type, details=""):
        """Adds a new event to the task's history."""
        if "history" not in task:
            task["history"] = []
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "agent_id": self.agent_id,
            "details": details
        }
        task["history"].append(event)
        task["updated_at"] = event["timestamp"]

    def add_task(self, description):
        """Adds a new task to the list."""
        if not self.acquire_lock():
            self._log("Failed to acquire lock. Task not added.")
            return None

        tasks = self.read_tasks()
        new_task_id = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc).isoformat()

        new_task = {
            "id": new_task_id,
            "description": description,
            "status": "PENDING",
            "assigned_to": None,
            "created_at": current_time,
            "updated_at": current_time,
            "history": [
                {
                    "timestamp": current_time,
                    "event": "CREATED",
                    "agent_id": self.agent_id, # Or None if system creates it
                    "details": "Task created"
                }
            ]
        }
        tasks.append(new_task)
        self.write_tasks(tasks)
        self.release_lock()
        self._log(f"Task '{new_task_id}' added: {description}")
        return new_task_id

    def update_task_status(self, task_id, new_status, expected_current_status=None):
        """Updates the status of a specific task."""
        allowed_statuses = ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"]
        if new_status not in allowed_statuses:
            self._log(f"Invalid status '{new_status}'. Task not updated.")
            return False

        if not self.acquire_lock():
            self._log(f"Failed to acquire lock. Task '{task_id}' not updated.")
            return False

        tasks = self.read_tasks()
        task_found = False
        for task in tasks:
            if task["id"] == task_id:
                task_found = True
                if expected_current_status and task["status"] != expected_current_status:
                    self._log(f"Task '{task_id}' status is '{task['status']}', expected '{expected_current_status}'. Update aborted.")
                    self.release_lock()
                    return False

                if task["status"] == new_status:
                    self._log(f"Task '{task_id}' is already '{new_status}'. No change made.")
                    self.release_lock()
                    # Return true as the state is already as desired.
                    return True

                old_status = task["status"]
                task["status"] = new_status
                details = f"Status changed from {old_status} to {new_status}"

                if new_status == "IN_PROGRESS":
                    task["assigned_to"] = self.agent_id
                    details += f", assigned to {self.agent_id}"
                elif new_status in ["COMPLETED", "FAILED"]:
                    # Optionally clear assignee, or leave for record
                    # task["assigned_to"] = None
                    pass

                self._add_history_event(task, "STATUS_CHANGED", details)
                self.write_tasks(tasks)
                self._log(f"Task '{task_id}' status updated to {new_status}.")
                break

        if not task_found:
            self._log(f"Task '{task_id}' not found. No update made.")

        self.release_lock()
        return task_found

    def get_pending_tasks(self):
        """Gets all tasks with PENDING status."""
        # No lock needed for read-only if eventual consistency is okay for this specific call.
        # However, for consistency in the agent's workflow, it might acquire a lock.
        # For now, let's assume a lock is acquired by the calling agent logic if needed.
        tasks = self.read_tasks()
        return [task for task in tasks if task["status"] == "PENDING"]

    def get_task(self, task_id):
        """Retrieves a single task by its ID."""
        tasks = self.read_tasks() # Similar to get_pending_tasks, lock might be managed externally
        for task in tasks:
            if task["id"] == task_id:
                return task
        return None

if __name__ == '__main__':
    # Example Usage (Illustrative - real agents would be separate processes)
    print("Starting Task Manager example...")

    # Initialize task file if it doesn't exist
    if not os.path.exists(TASK_FILE):
        with open(TASK_FILE, "w") as f:
            json.dump([], f)
        print(f"{TASK_FILE} initialized.")

    agent1_task_manager = TaskManager(agent_id="Agent1")
    agent2_task_manager = TaskManager(agent_id="Agent2")

    # Agent 1 adds a task
    print("\n--- Agent1 Operations ---")
    task_id_1 = agent1_task_manager.add_task("Process dataset X")
    if task_id_1:
        print(f"Agent1 added task: {task_id_1}")

    # Agent 2 tries to pick up a task
    print("\n--- Agent2 Operations ---")
    if agent2_task_manager.acquire_lock():
        pending_tasks_agent2 = agent2_task_manager.read_tasks() # Reading all for this example
        print(f"Agent2 sees tasks: {json.dumps(pending_tasks_agent2, indent=2)}")

        task_to_take = None
        for t in pending_tasks_agent2:
            if t["status"] == "PENDING":
                task_to_take = t
                break

        if task_to_take:
            print(f"Agent2 attempting to take task: {task_to_take['id']}")
            # Agent2 updates the status to IN_PROGRESS
            # In a real scenario, update_task_status would be used directly
            task_to_take["status"] = "IN_PROGRESS"
            task_to_take["assigned_to"] = agent2_task_manager.agent_id
            agent2_task_manager._add_history_event(task_to_take, "STATUS_CHANGED", f"Status changed from PENDING to IN_PROGRESS, assigned to {agent2_task_manager.agent_id}")
            agent2_task_manager.write_tasks(pending_tasks_agent2) # Write the modified list
            print(f"Agent2 took task {task_to_take['id']}")
        else:
            print("Agent2 found no pending tasks to take.")
        agent2_task_manager.release_lock()
    else:
        print("Agent2 could not acquire lock for operations.")

    # Agent 1 tries to complete its (now taken) task - this will fail due to current logic
    # or show it's already IN_PROGRESS by Agent2
    print("\n--- Agent1 Operations (Post Agent2) ---")
    if task_id_1:
        # agent1_task_manager.update_task_status(task_id_1, "COMPLETED", expected_current_status="IN_PROGRESS")
        # This would require Agent1 to have it assigned. Let's just read for now.
        if agent1_task_manager.acquire_lock():
            task_check_agent1 = agent1_task_manager.get_task(task_id_1)
            print(f"Agent1 sees task {task_id_1} as: {json.dumps(task_check_agent1, indent=2)}")
            agent1_task_manager.release_lock()
        else:
            print(f"Agent1 could not acquire lock to check task {task_id_1}")


    # Agent 2 completes its task
    print("\n--- Agent2 Operations (Completion) ---")
    if task_to_take: # task_to_take is from Agent2's scope earlier
        success = agent2_task_manager.update_task_status(task_to_take['id'], "COMPLETED", expected_current_status="IN_PROGRESS")
        if success:
            print(f"Agent2 completed task {task_to_take['id']}.")
        else:
            print(f"Agent2 failed to complete task {task_to_take['id']} (status mismatch or lock issue).")

    print("\nFinal tasks state:")
    if agent1_task_manager.acquire_lock(): # Use one agent to print final state
        final_tasks = agent1_task_manager.read_tasks()
        print(json.dumps(final_tasks, indent=2))
        agent1_task_manager.release_lock()
    else:
        print("Could not acquire lock to show final tasks state.")

    # Clean up lock file if it exists
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        print(f"\n{LOCK_FILE} cleaned up.")
    # if os.path.exists(TASK_FILE):
    #     os.remove(TASK_FILE)
    #     print(f"{TASK_FILE} cleaned up.")

print("Task Manager example finished.")
