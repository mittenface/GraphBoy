import argparse
import json
import os
import uuid
import time
from datetime import datetime, timezone

# Assuming TaskManager class is defined here or imported
# For CLI, we might duplicate some TaskManager logic or make it importable
# For simplicity, relevant parts of TaskManager logic for file operations will be included/adapted.

TASK_FILE_DEFAULT = "tasks.json"
LOCK_FILE_DEFAULT = "tasks.lock"
STALE_TIMEOUT_DEFAULT = 300  # 5 minutes

# --- Minimal Lock Management for CLI ---
_cli_agent_id = f"cli_user_{os.getpid()}"
_lock_file_path_cli = LOCK_FILE_DEFAULT # Will be updated by args in main()

def acquire_lock_cli(lock_file_path, agent_id, stale_timeout):
    start_time = time.time()
    max_wait_time = 15 # Max wait for CLI, can be shorter than agent's
    retry_interval = 1

    while (time.time() - start_time) < max_wait_time:
        if not os.path.exists(lock_file_path):
            try:
                with open(lock_file_path, "w") as f:
                    json.dump({"agent_id": agent_id, "timestamp": datetime.now(timezone.utc).isoformat()}, f)
                # print(f"CLI acquired lock: {lock_file_path}")
                return True
            except IOError:
                pass # Retry
        else:
            try:
                with open(lock_file_path, "r") as f:
                    lock_data = json.load(f)
                lock_time_str = lock_data.get("timestamp")
                if lock_time_str:
                    lock_time = datetime.fromisoformat(lock_time_str.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - lock_time).total_seconds() > stale_timeout:
                        print(f"Warning: Found stale lock from {lock_data.get('agent_id')} (acquired at {lock_time_str}). Breaking lock.")
                        os.remove(lock_file_path)
                        continue # Try to acquire immediately
            except (IOError, json.JSONDecodeError, ValueError) as e:
                print(f"Warning: Error reading or parsing lock file {lock_file_path}: {e}. Assuming held.")

        # print(f"CLI waiting for lock: {lock_file_path}")
        time.sleep(retry_interval)

    print(f"Error: CLI failed to acquire lock on {lock_file_path} within {max_wait_time}s.")
    return False

def release_lock_cli(lock_file_path, agent_id):
    if not os.path.exists(lock_file_path):
        # print(f"CLI: No lock file {lock_file_path} to release.")
        return True
    try:
        with open(lock_file_path, "r") as f:
            lock_data = json.load(f)
        if lock_data.get("agent_id") == agent_id:
            os.remove(lock_file_path)
            # print(f"CLI released lock: {lock_file_path}")
            return True
        else:
            # This can happen if stale lock was broken by another CLI instance after this one acquired it.
            if not os.path.exists(lock_file_path): # Check if file was removed by another process
                 # print(f"CLI: Lock file {lock_file_path} was already removed (possibly by another process breaking a stale lock).")
                 return True
            print(f"Warning: CLI cannot release lock for {lock_file_path}. Held by: {lock_data.get('agent_id')}, this CLI is: {agent_id}.")
            return False
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error releasing lock {lock_file_path}: {e}. Manual check may be needed.")
        return False

# --- Helper Functions for CLI ---
def read_data_cli(task_file_path):
    if not os.path.exists(task_file_path):
        return {"task_pairs": [], "tasks": []} # Return default structure if no file
    try:
        with open(task_file_path, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing {task_file_path}: {e}")
        return None

def write_data_cli(task_file_path, data):
    try:
        with open(task_file_path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except IOError as e:
        print(f"Error writing to {task_file_path}: {e}")
        return False

def _add_history_event_cli(item, event_type, details="", by_agent=_cli_agent_id):
    """Adds a history event to a task or a pair."""
    if "history" not in item or item["history"] is None: # Check for None explicitly
        item["history"] = []

    timestamp = datetime.now(timezone.utc).isoformat()
    event = {
        "timestamp": timestamp,
        "event": event_type,
        "agent_id": by_agent,
        "details": str(details)
    }
    item["history"].append(event)
    # Tasks have updated_at. Pairs will also get it if this function is used for them.
    item["updated_at"] = timestamp


# --- CLI Command Functions ---
def init_tasks_file(args):
    global _lock_file_path_cli # Ensure we use the path from args
    _lock_file_path_cli = args.lock_file


    if os.path.exists(args.task_file) and not args.force:
        print(f"Error: Task file '{args.task_file}' already exists. Use --force to overwrite.")
        return

    # No lock needed for init if --force, as it's a destructive operation anyway.
    # If not --force and file doesn't exist, also no lock needed yet.
    # Lock primarily protects read-modify-write cycles.
    # However, to be consistent and prevent race with other CLI/agents trying to init:
    if not acquire_lock_cli(args.lock_file, _cli_agent_id, args.stale_timeout): return


    try:
        initial_data = {"task_pairs": [], "tasks": []}
        if write_data_cli(args.task_file, initial_data):
            print(f"Task file '{args.task_file}' initialized successfully.")
    finally:
        release_lock_cli(args.lock_file, _cli_agent_id)

def add_task(args):
    global _lock_file_path_cli
    _lock_file_path_cli = args.lock_file
    if not acquire_lock_cli(args.lock_file, _cli_agent_id, args.stale_timeout): return

    try:
        data = read_data_cli(args.task_file)
        if data is None: return

        task_id = args.task_id if args.task_id else str(uuid.uuid4())

        if any(t['id'] == task_id for t in data.get('tasks', [])):
            print(f"Error: Task ID '{task_id}' already exists.")
            return

        new_task = {
            "id": task_id,
            "pair_id": args.pair_id,
            "agent_preference": args.agent_pref,
            "description": args.desc,
            "status": "PENDING",
            "assigned_to": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "history": []
        }
        _add_history_event_cli(new_task, "CREATED", f"Task created via CLI by {_cli_agent_id}")

        data.setdefault("tasks", []).append(new_task)

        if write_data_cli(args.task_file, data):
            print(f"Task '{task_id}' added successfully: {args.desc}")
    finally:
        release_lock_cli(args.lock_file, _cli_agent_id)

def add_pair(args):
    global _lock_file_path_cli
    _lock_file_path_cli = args.lock_file
    if not acquire_lock_cli(args.lock_file, _cli_agent_id, args.stale_timeout): return

    try:
        data = read_data_cli(args.task_file)
        if data is None: return

        all_task_ids = [t['id'] for t in data.get('tasks', [])]
        if args.task_id1 not in all_task_ids:
            print(f"Error: task_id1 '{args.task_id1}' not found in existing tasks.")
            return
        if args.task_id2 not in all_task_ids:
            print(f"Error: task_id2 '{args.task_id2}' not found in existing tasks.")
            return
        if args.task_id1 == args.task_id2:
            print(f"Error: task_id1 and task_id2 cannot be the same.")
            return

        pair_id = args.pair_id if args.pair_id else f"pair_{str(uuid.uuid4())[:8]}"

        if any(p['pair_id'] == pair_id for p in data.get('task_pairs', [])):
            print(f"Error: Pair ID '{pair_id}' already exists.")
            return
        if any(p['sequence_index'] == args.seq_idx for p in data.get('task_pairs', [])):
            print(f"Warning: sequence_index {args.seq_idx} is already in use for another pair. This might lead to ordering issues if not intended.")


        status = args.status if args.status else "BLOCKED"
        pair_lock = args.lock
        if pair_lock is None:
            pair_lock = True if status == "BLOCKED" else False

        new_pair = {
            "pair_id": pair_id,
            "tasks": [args.task_id1, args.task_id2],
            "status": status,
            "pair_lock": pair_lock,
            "sequence_index": args.seq_idx,
            "history": [],
            "created_at": datetime.now(timezone.utc).isoformat(), # Add created_at for pairs
            "updated_at": datetime.now(timezone.utc).isoformat()  # Add updated_at for pairs
        }
        _add_history_event_cli(new_pair, "CREATED", f"Pair created via CLI by {_cli_agent_id}")


        for i, task_obj in enumerate(data["tasks"]):
            if task_obj["id"] == args.task_id1 or task_obj["id"] == args.task_id2:
                if task_obj.get("pair_id") and task_obj.get("pair_id") != pair_id :
                     print(f"Warning: Task {task_obj['id']} was already part of pair {task_obj['pair_id']}. Overwriting with {pair_id}.")
                data["tasks"][i]["pair_id"] = pair_id
                _add_history_event_cli(data["tasks"][i], "UPDATED", f"Associated with pair_id {pair_id} via CLI")


        data.setdefault("task_pairs", []).append(new_pair)

        if write_data_cli(args.task_file, data):
            print(f"Task pair '{pair_id}' added successfully with tasks '{args.task_id1}', '{args.task_id2}' at sequence {args.seq_idx}.")
    finally:
        release_lock_cli(args.lock_file, _cli_agent_id)


def create_full_pair(args):
    global _lock_file_path_cli
    _lock_file_path_cli = args.lock_file
    if not acquire_lock_cli(args.lock_file, _cli_agent_id, args.stale_timeout): return

    try:
        data = read_data_cli(args.task_file)
        if data is None: return

        pair_id_prefix = args.pair_id if args.pair_id else f"fp_{str(uuid.uuid4())[:4]}"

        task_id1 = f"{pair_id_prefix}_t1"
        task_id2 = f"{pair_id_prefix}_t2"
        actual_pair_id = f"{pair_id_prefix}_p"

        existing_ids = set(t['id'] for t in data.get('tasks', [])) | set(p['pair_id'] for p in data.get('task_pairs', []))
        if task_id1 in existing_ids or task_id2 in existing_ids or actual_pair_id in existing_ids:
            print(f"Error: Generated ID collision for prefix '{pair_id_prefix}'. Try a different prefix or ensure IDs are unique manually.")
            return
        if any(p['sequence_index'] == args.seq_idx for p in data.get('task_pairs', [])):
            print(f"Warning: sequence_index {args.seq_idx} is already in use. This might lead to ordering issues if not intended.")

        current_ts = datetime.now(timezone.utc).isoformat()
        task1 = {
            "id": task_id1, "pair_id": actual_pair_id, "agent_preference": args.agent1,
            "description": args.desc1, "status": "PENDING", "assigned_to": None,
            "created_at": current_ts, "updated_at": current_ts, "history": []
        }
        _add_history_event_cli(task1, "CREATED", f"Task created as part of full pair by {_cli_agent_id}")
        data.setdefault("tasks", []).append(task1)

        task2 = {
            "id": task_id2, "pair_id": actual_pair_id, "agent_preference": args.agent2,
            "description": args.desc2, "status": "PENDING", "assigned_to": None,
            "created_at": current_ts, "updated_at": current_ts, "history": []
        }
        _add_history_event_cli(task2, "CREATED", f"Task created as part of full pair by {_cli_agent_id}")
        data.setdefault("tasks", []).append(task2)

        new_pair = {
            "pair_id": actual_pair_id, "tasks": [task_id1, task_id2],
            "status": "BLOCKED", "pair_lock": True,
            "sequence_index": args.seq_idx, "history": [],
            "created_at": current_ts, "updated_at": current_ts
        }
        _add_history_event_cli(new_pair, "CREATED", f"Pair created as part of full pair by {_cli_agent_id}")

        data.setdefault("task_pairs", []).append(new_pair)

        if write_data_cli(args.task_file, data):
            print(f"Full pair '{actual_pair_id}' created with tasks '{task_id1}' ({args.agent1}: {args.desc1}) and '{task_id2}' ({args.agent2}: {args.desc2}) at sequence {args.seq_idx}.")
    finally:
        release_lock_cli(args.lock_file, _cli_agent_id)


def get_status(args):
    data = read_data_cli(args.task_file) # Read-only, no lock needed generally
    if data is None: return

    output_data = {}
    if args.pair_id:
        pair = next((p for p in data.get("task_pairs", []) if p["pair_id"] == args.pair_id), None)
        if pair:
            output_data["pair"] = pair
            output_data["associated_tasks"] = []
            for task_id in pair.get("tasks", []):
                task = next((t for t in data.get("tasks", []) if t["id"] == task_id), None)
                if task: output_data["associated_tasks"].append(task)
                else: output_data["associated_tasks"].append({"id": task_id, "error": "Not Found"})
        else:
            output_data["error"] = f"Pair ID '{args.pair_id}' not found."
    elif args.task_id:
        task = next((t for t in data.get("tasks", []) if t["id"] == args.task_id), None)
        if task: output_data["task"] = task
        else: output_data["error"] = f"Task ID '{args.task_id}' not found."
    else:
        output_data = data # Full status

    print(json.dumps(output_data, indent=2))

def advance_next_pair_cmd(args):
    global _lock_file_path_cli
    _lock_file_path_cli = args.lock_file
    if not acquire_lock_cli(args.lock_file, _cli_agent_id, args.stale_timeout): return

    try:
        data = read_data_cli(args.task_file)
        if data is None: return

        task_pairs = sorted([p for p in data.get("task_pairs", []) if isinstance(p,dict)], key=lambda p: p.get("sequence_index", float('inf')))

        last_completed_seq_idx = -1
        if not args.force: # If --force, we skip finding a completed pair and just advance the lowest BLOCKED.
            found_completed_for_basis = False
            for pair in reversed(task_pairs):
                if pair.get("status") == "COMPLETED":
                    last_completed_seq_idx = pair.get("sequence_index", -1)
                    found_completed_for_basis = True
                    break
            if not found_completed_for_basis and task_pairs:
                 print("No COMPLETED task pairs found to determine the 'next' one. Use --force to advance the lowest index BLOCKED pair (e.g. the first pair).")
                 return

        pair_to_advance_candidate = None
        candidate_idx_in_data = -1

        for i, pair_obj in enumerate(data.get("task_pairs", [])): # Iterate original to get index
            current_pair_seq_idx = pair_obj.get("sequence_index", float('inf'))
            if pair_obj.get("status") == "BLOCKED":
                if args.force and (pair_to_advance_candidate is None or current_pair_seq_idx < pair_to_advance_candidate.get("sequence_index", float('inf'))):
                    pair_to_advance_candidate = pair_obj
                    candidate_idx_in_data = i
                elif not args.force and current_pair_seq_idx > last_completed_seq_idx:
                    if pair_to_advance_candidate is None or current_pair_seq_idx < pair_to_advance_candidate.get("sequence_index", float('inf')):
                         pair_to_advance_candidate = pair_obj
                         candidate_idx_in_data = i

        if pair_to_advance_candidate and candidate_idx_in_data != -1:
            # Directly modify the object in the data["task_pairs"] list via its original index
            data["task_pairs"][candidate_idx_in_data]["status"] = "READY"
            data["task_pairs"][candidate_idx_in_data]["pair_lock"] = False
            _add_history_event_cli(data["task_pairs"][candidate_idx_in_data], "STATUS_CHANGED", f"Pair advanced to READY via CLI by {_cli_agent_id}")

            if write_data_cli(args.task_file, data):
                print(f"Task pair '{data['task_pairs'][candidate_idx_in_data]['pair_id']}' (Seq: {data['task_pairs'][candidate_idx_in_data]['sequence_index']}) advanced to READY and unlocked.")
        else:
            msg = "No suitable BLOCKED pair found to advance."
            if not args.force and last_completed_seq_idx != -1:
                 msg += f" (after sequence {last_completed_seq_idx})."
            elif not task_pairs:
                 msg = "No task pairs exist in the file."
            print(msg)
    finally:
        release_lock_cli(args.lock_file, _cli_agent_id)


def validate_tasks_file(args):
    data = read_data_cli(args.task_file) # Read-only
    if data is None: return

    errors = []
    warnings = []
    task_ids = set()

    for task in data.get("tasks", []):
        if not isinstance(task, dict):
            errors.append(f"Invalid task entry found (not a dictionary): {str(task)[:50]}")
            continue
        tid = task.get("id")
        if not tid: errors.append(f"Task found with missing ID: {str(task)[:50]}")
        elif tid in task_ids: errors.append(f"Duplicate task ID: {tid}")
        else: task_ids.add(tid)

        if task.get("pair_id") and not any(p.get("pair_id") == task.get("pair_id") for p in data.get("task_pairs",[])):
            errors.append(f"Task '{tid}' has orphaned pair_id '{task.get('pair_id')}' (pair does not exist).")

    pair_ids = set()
    seq_indices = {} # Store as {index: [pair_id1, pair_id2]} to detect duplicates
    for pair in data.get("task_pairs", []):
        if not isinstance(pair, dict):
            errors.append(f"Invalid task_pair entry found (not a dictionary): {str(pair)[:50]}")
            continue
        pid = pair.get("pair_id")
        if not pid: errors.append(f"Task pair found with missing pair_id: {str(pair)[:50]}")
        elif pid in pair_ids: errors.append(f"Duplicate pair ID: {pid}")
        else: pair_ids.add(pid)

        seq_idx = pair.get("sequence_index")
        if seq_idx is None: errors.append(f"Pair '{pid}' has missing sequence_index.")
        elif not isinstance(seq_idx, int): errors.append(f"Pair '{pid}' sequence_index is not an integer: {seq_idx}")
        else:
            if seq_idx in seq_indices: seq_indices[seq_idx].append(pid)
            else: seq_indices[seq_idx] = [pid]

        task_refs = pair.get("tasks", [])
        if not isinstance(task_refs, list) or len(task_refs) != 2:
            errors.append(f"Pair '{pid}' tasks field is not a list of two task IDs (found {len(task_refs) if isinstance(task_refs, list) else 'non-list'}).")
        for task_id in task_refs:
            if task_id not in task_ids:
                errors.append(f"Pair '{pid}' references non-existent task ID: {task_id}")

    for idx, pids in seq_indices.items():
        if len(pids) > 1:
            warnings.append(f"Duplicate sequence_index: {idx} used by pairs: {', '.join(pids)}. This may cause non-deterministic ordering.")

    if errors:
        print("Validation Errors Found:")
        for err in errors: print(f"  - {err}")
    if warnings:
        print("Validation Warnings Found:")
        for warn in warnings: print(f"  - {warn}")

    if not errors and not warnings:
        print("Validation successful: No errors or warnings found.")
    elif not errors and warnings:
        print("Validation successful: No errors found, but there are warnings.")


def main_cli():
    parser = argparse.ArgumentParser(description="Task Manager CLI for synchronized task pairs.")
    # Ensure global _lock_file_path_cli is set from args early if possible, or pass args to functions that use it.
    # For now, functions will re-assign it from their args.
    parser.add_argument('--task-file', default=TASK_FILE_DEFAULT, help=f"Path to the tasks JSON file (default: {TASK_FILE_DEFAULT})")
    parser.add_argument('--lock-file', default=LOCK_FILE_DEFAULT, help=f"Path to the lock file (default: {LOCK_FILE_DEFAULT})")
    parser.add_argument('--stale-timeout', type=int, default=STALE_TIMEOUT_DEFAULT, help=f"Stale lock timeout in seconds (default: {STALE_TIMEOUT_DEFAULT})")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    p_init = subparsers.add_parser("init", help="Initialize or re-initialize the tasks file.")
    p_init.add_argument("--force", action="store_true", help="Overwrite tasks.json if it already exists.")
    p_init.set_defaults(func=init_tasks_file)

    p_add_task = subparsers.add_parser("add_task", help="Add a new individual task.")
    p_add_task.add_argument("--desc", required=True, help="Description of the task.")
    p_add_task.add_argument("--agent_pref", default=None, help="Preferred agent ID for this task.")
    p_add_task.add_argument("--pair_id", default=None, help="Optionally assign this task to an existing pair ID.")
    p_add_task.add_argument("--task_id", default=None, help="Specify a custom task ID (default: UUID).")
    p_add_task.set_defaults(func=add_task)

    p_add_pair = subparsers.add_parser("add_pair", help="Create a new task pair from existing tasks.")
    p_add_pair.add_argument("--task_id1", required=True, help="ID of the first task in the pair.")
    p_add_pair.add_argument("--task_id2", required=True, help="ID of the second task in the pair.")
    p_add_pair.add_argument("--seq_idx", required=True, type=int, help="Sequence index for this pair.")
    p_add_pair.add_argument("--pair_id", default=None, help="Specify a custom pair ID (default: 'pair_' + UUID).")
    p_add_pair.add_argument("--status", choices=["BLOCKED", "READY", "COMPLETED"], default="BLOCKED", help="Initial status of the pair (default: BLOCKED).")
    p_add_pair.add_argument("--lock", type=lambda x: (str(x).lower() == 'true'), default=None, help="Set pair_lock (true/false). Defaults based on status.")
    p_add_pair.set_defaults(func=add_pair)

    p_create_fp = subparsers.add_parser("create_full_pair", help="Convenience command to create two new tasks and a pair linking them.")
    p_create_fp.add_argument("--desc1", required=True, help="Description for the first task.")
    p_create_fp.add_argument("--agent1", default=None, help="Preferred agent for the first task.")
    p_create_fp.add_argument("--desc2", required=True, help="Description for the second task.")
    p_create_fp.add_argument("--agent2", default=None, help="Preferred agent for the second task.")
    p_create_fp.add_argument("--seq_idx", required=True, type=int, help="Sequence index for the new pair.")
    p_create_fp.add_argument("--pair_id", default=None, help="Optional custom prefix for generated pair and task IDs (e.g., 'my_job').")
    p_create_fp.set_defaults(func=create_full_pair)

    p_status = subparsers.add_parser("status", help="Display status of tasks and pairs.")
    p_status.add_argument("--pair_id", default=None, help="Display status for a specific pair ID.")
    p_status.add_argument("--task_id", default=None, help="Display status for a specific task ID.")
    p_status.set_defaults(func=get_status)

    p_advance = subparsers.add_parser("advance_next_pair", help="Manually advance the next BLOCKED pair to READY.")
    p_advance.add_argument("--force", action="store_true", help="Force advancement even if no COMPLETED pair is found (e.g., for the first pair or to unblock any lowest BLOCKED).")
    p_advance.set_defaults(func=advance_next_pair_cmd)

    p_validate = subparsers.add_parser("validate", help="Validate the integrity of the tasks.json file.")
    p_validate.set_defaults(func=validate_tasks_file)

    args = parser.parse_args()

    # Make sure the global _lock_file_path_cli is updated from args before any function that might use it is called.
    # This is a bit of a workaround for not passing 'args' to every lock function.
    global _lock_file_path_cli
    _lock_file_path_cli = args.lock_file


    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main_cli()
```
