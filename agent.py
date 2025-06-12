import time
import random
import json # Added for potential debugging, can be removed if not used directly
import os # Added for checking file existence, can be removed if TaskManager handles all
from task_manager import TaskManager # Assuming TaskManager is in task_manager.py

class Agent:
    def __init__(self, agent_id, task_file="tasks.json", lock_file="tasks.lock", stale_timeout=300):
        self.agent_id = agent_id
        self.task_manager = TaskManager(agent_id=self.agent_id, task_file=task_file, lock_file=lock_file, stale_timeout=stale_timeout)
        self._log(f"Agent initialized. Managing file: {task_file}")

    def _log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        print(f"{timestamp} [{self.agent_id}] [{level.upper()}]: {message}")

    def perform_task_work(self, task):
        self._log(f"Starting work on task '{task['id']}': '{task['description']}'")
        work_duration = random.uniform(1, 3)  # Simulate 1-3 seconds of work
        time.sleep(work_duration)

        # Simulate success or failure (can be made more complex)
        succeeded = random.choices([True, False], weights=[0.9, 0.1], k=1)[0] # 90% chance of success

        if succeeded:
            self._log(f"Successfully completed task '{task['id']}'.")
            return "COMPLETED"
        else:
            self._log(f"Failed to complete task '{task['id']}'.", level="ERROR")
            return "FAILED"

    def process_tasks_once(self):
        self._log("Attempting to process tasks...")

        if not self.task_manager.acquire_lock():
            self._log("Could not acquire lock. Will retry later.", level="WARNING")
            return False # Indicate no action was taken this cycle

        try:
            data = self.task_manager.read_data()
            if not data:
                self._log("Task data is empty or could not be read.", level="WARNING")
                return False

            task_pairs = sorted([p for p in data.get("task_pairs", []) if isinstance(p, dict)], key=lambda p: p.get("sequence_index", float('inf')))
            all_tasks = {task['id']: task for task in data.get("tasks", []) if isinstance(task, dict)}

            active_pair = None
            for pair in task_pairs:
                if pair.get("status") == "READY" and not pair.get("pair_lock", False):
                    active_pair = pair
                    break

            if not active_pair:
                self._log("No READY and unlocked task pairs found.")
                return False # No active pair to process

            self._log(f"Found active pair: {active_pair['pair_id']} (Seq: {active_pair['sequence_index']})")

            claimed_task_this_cycle = False
            for task_id_in_pair in active_pair.get("tasks", []):
                task = all_tasks.get(task_id_in_pair)
                if not task:
                    self._log(f"Task ID '{task_id_in_pair}' in pair '{active_pair['pair_id']}' not found in tasks list. Skipping.", level="ERROR")
                    continue

                if task.get("status") == "PENDING" and \
                   (task.get("agent_preference") == self.agent_id or not task.get("agent_preference")) and \
                   task.get("assigned_to") is None: # Ensure it's not already assigned

                    self._log(f"Attempting to claim task '{task['id']}' from pair '{active_pair['pair_id']}'.")
                    task["status"] = "IN_PROGRESS"
                    task["assigned_to"] = self.agent_id
                    self.task_manager._add_history_event(task, "ASSIGNED", f"Assigned to and claimed by {self.agent_id}")

                    # Update the main data structure
                    for i, t in enumerate(data["tasks"]):
                        if t["id"] == task["id"]:
                            data["tasks"][i] = task
                            break

                    self.task_manager.write_data(data)
                    self._log(f"Task '{task['id']}' claimed and status set to IN_PROGRESS.")
                    claimed_task_this_cycle = True

                    # --- Perform work AFTER releasing initial lock ---
                    self.task_manager.release_lock()
                    self._log(f"Lock released before performing work for task '{task['id']}'.")

                    final_status = self.perform_task_work(task)

                    # --- Re-acquire lock to update final status ---
                    if not self.task_manager.acquire_lock():
                        self._log(f"CRITICAL: Could not re-acquire lock to finalize task '{task['id']}'. Status: {final_status}. Manual intervention may be needed.", level="ERROR")
                        # This is a problematic state. The task is done but its state isn't in JSON.
                        # Options: retry, queue for later update, or flag for manual fix.
                        return True # Still counts as work done, but with error.

                    try:
                        # Re-read data as it might have changed
                        current_data_for_finalizing = self.task_manager.read_data()
                        if not current_data_for_finalizing:
                             self._log(f"CRITICAL: Could not read data to finalize task '{task['id']}'.", level="ERROR")
                             return True # Work done, error in finalizing

                        task_to_finalize = None
                        for i, t_final in enumerate(current_data_for_finalizing["tasks"]):
                            if t_final["id"] == task["id"]:
                                task_to_finalize = t_final
                                break

                        if not task_to_finalize:
                            self._log(f"Task '{task['id']}' no longer found in data file upon trying to finalize. Perhaps deleted or changed?", level="ERROR")
                            return True # Work done, error in finalizing

                        if task_to_finalize.get("assigned_to") != self.agent_id:
                            self._log(f"Task '{task['id']}' was reassigned from {self.agent_id} to {task_to_finalize.get('assigned_to')} before finalization. Not updating.", level="WARNING")
                            return True # Work done by this agent, but another took over.

                        task_to_finalize["status"] = final_status
                        # task_to_finalize["assigned_to"] = None # Optional: clear assignee on completion/failure
                        self.task_manager._add_history_event(task_to_finalize, "STATUS_CHANGED", f"Status changed to {final_status} by {self.agent_id}")
                        current_data_for_finalizing["tasks"][i] = task_to_finalize # Update in the list

                        self._log(f"Task '{task['id']}' finalized with status '{final_status}'.")

                        # Check for pair completion
                        pair_of_this_task = None
                        for p_idx, p_check in enumerate(current_data_for_finalizing["task_pairs"]):
                            if p_check["pair_id"] == task_to_finalize.get("pair_id"):
                                pair_of_this_task = p_check
                                break

                        if pair_of_this_task:
                            all_tasks_in_pair_completed = True
                            for t_id_in_pair_check in pair_of_this_task["tasks"]:
                                t_check = next((t for t in current_data_for_finalizing["tasks"] if t["id"] == t_id_in_pair_check), None)
                                if not t_check or t_check["status"] != "COMPLETED":
                                    all_tasks_in_pair_completed = False
                                    break

                            if all_tasks_in_pair_completed:
                                self._log(f"All tasks in pair '{pair_of_this_task['pair_id']}' are COMPLETED.")
                                pair_of_this_task["status"] = "COMPLETED"
                                pair_of_this_task["pair_lock"] = True # Lock completed pair
                                self.task_manager._add_history_event_to_pair(pair_of_this_task, "STATUS_CHANGED", f"Pair status changed to COMPLETED by {self.agent_id}")


                                # Advance next pair
                                current_seq_idx = pair_of_this_task["sequence_index"]
                                next_pair_to_unlock = None
                                min_next_seq_idx = float('inf')

                                for p_next_check_idx, p_next_check in enumerate(current_data_for_finalizing["task_pairs"]):
                                    if p_next_check.get("sequence_index", float('inf')) > current_seq_idx and \
                                       p_next_check.get("status") == "BLOCKED":
                                        if p_next_check.get("sequence_index") < min_next_seq_idx:
                                            min_next_seq_idx = p_next_check.get("sequence_index")
                                            # Store index for direct modification
                                            next_pair_to_unlock = (p_next_check_idx, p_next_check)


                                if next_pair_to_unlock:
                                    pair_obj_to_unlock_idx, pair_obj_to_unlock = next_pair_to_unlock
                                    self._log(f"Advancing next pair: '{pair_obj_to_unlock['pair_id']}' (Seq: {pair_obj_to_unlock['sequence_index']}) to READY.")
                                    current_data_for_finalizing["task_pairs"][pair_obj_to_unlock_idx]["status"] = "READY"
                                    current_data_for_finalizing["task_pairs"][pair_obj_to_unlock_idx]["pair_lock"] = False
                                    self.task_manager._add_history_event_to_pair(current_data_for_finalizing["task_pairs"][pair_obj_to_unlock_idx], "STATUS_CHANGED", f"Pair status changed to READY by {self.agent_id} (advancement)")

                        self.task_manager.write_data(current_data_for_finalizing)
                        # Lock will be released by the finally block

                    except Exception as e_finalize:
                        self._log(f"CRITICAL ERROR during task finalization for '{task['id']}': {e_finalize}", level="ERROR")
                        # Lock should still be released by finally

                    return True # Task was processed

            if not claimed_task_this_cycle:
                self._log("No suitable PENDING tasks found for this agent in the active pair or preference mismatch.")
                return False # No task processed by this agent in this cycle

        except Exception as e:
            self._log(f"Error during task processing: {e}", level="ERROR")
            # Ensure lock is released if acquired and an error occurs mid-process
            # The TaskManager's release_lock should be safe to call even if not currently held by this agent instance in some edge cases,
            # but ideally, we only call it if we know we hold it.
            # The current structure has release_lock in finally, which is good.
            return False # Error occurred
        finally:
            self.task_manager.release_lock() # Ensure lock is always released

        return False # Should be covered by return True if task processed.

    def run(self, cycles=None, interval=10):
        self._log(f"Starting run loop. Max cycles: {'infinite' if cycles is None else cycles}. Interval: {interval}s.")
        executed_cycles = 0
        while cycles is None or executed_cycles < cycles:
            try:
                processed_something = self.process_tasks_once()
                if processed_something:
                    self._log(f"Cycle {executed_cycles + 1}: Task processing attempted/completed.")
                else:
                    self._log(f"Cycle {executed_cycles + 1}: No tasks processed or available for this agent.")
            except Exception as e:
                self._log(f"Unhandled error in agent run loop: {e}", level="CRITICAL")

            executed_cycles += 1
            if cycles is not None and executed_cycles >= cycles:
                break

            self._log(f"Waiting {interval} seconds for next cycle...")
            time.sleep(interval)
        self._log("Run loop finished.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run a task processing agent.")
    parser.add_argument("agent_id", help="Unique ID for this agent (e.g., Agent1)")
    parser.add_argument("--task-file", default="tasks.json", help="Path to the tasks JSON file.")
    parser.add_argument("--lock-file", default="tasks.lock", help="Path to the lock file.")
    parser.add_argument("--cycles", type=int, default=None, help="Number of processing cycles to run (default: infinite).")
    parser.add_argument("--interval", type=int, default=10, help="Interval in seconds between processing cycles.")
    parser.add_argument("--stale-timeout", type=int, default=300, help="Timeout in seconds for considering a lock stale.")

    args = parser.parse_args()

    # Basic check for tasks.json initialization
    if not os.path.exists(args.task_file):
        print(f"Error: Task file '{args.task_file}' not found. Please initialize it using task_manager_cli.py first.", level="ERROR")
        exit(1)
    try:
        with open(args.task_file, 'r') as f:
            init_data = json.load(f)
        if not isinstance(init_data, dict) or "tasks" not in init_data or "task_pairs" not in init_data:
            print(f"Error: Task file '{args.task_file}' is not correctly initialized. Expected a JSON object with 'tasks' and 'task_pairs' arrays.", level="ERROR")
            exit(1)
    except json.JSONDecodeError:
        print(f"Error: Task file '{args.task_file}' contains invalid JSON.", level="ERROR")
        exit(1)


    agent = Agent(
        agent_id=args.agent_id,
        task_file=args.task_file,
        lock_file=args.lock_file,
        stale_timeout=args.stale_timeout
    )
    agent.run(cycles=args.cycles, interval=args.interval)
```
