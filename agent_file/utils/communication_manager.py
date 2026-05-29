"""
Multi-Agent Communication Manager
Handles inter-agent communication via target.js and provides comprehensive tracing
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FileCommunicationManager:
    """Manages inter-agent communication through target.js (file-backed)
    Kept for backward compatibility and development setups without Redis/SQLite.
    """

    def __init__(self, target_file_path: str = None):
        """
        Initialize the communication manager
        
        Args:
            target_file_path: Path to target.js file (defaults to agent_file/target.js)
        """
        if target_file_path is None:
            # Auto-detect the path
            current_dir = Path(__file__).parent.parent
            target_file_path = current_dir / "target.js"
        
        self.target_path = Path(target_file_path)
        self.lock_file = str(self.target_path) + ".lock"
        self.backup_path = str(self.target_path) + ".backup"
        
    def read_state(self) -> Dict[str, Any]:
        """Read current workflow state from target.js"""
        try:
            if self.target_path.exists():
                with open(self.target_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Remove 'module.exports = ' prefix if present
                    if content.startswith('module.exports ='):
                        content = content.replace('module.exports =', '', 1)
                    # Remove trailing semicolon
                    content = content.rstrip(';').strip()
                    return json.loads(content)
            else:
                logger.warning(f"Target file not found: {self.target_path}")
                return self._get_default_state()
        except Exception as e:
            logger.error(f"Error reading state: {e}")
            return self._get_default_state()
    
    def write_state(self, state: Dict[str, Any]) -> bool:
        """Write workflow state to target.js"""
        try:
            # Create backup before writing
            if self.target_path.exists():
                with open(self.target_path, 'r', encoding='utf-8') as f:
                    with open(self.backup_path, 'w', encoding='utf-8') as backup:
                        backup.write(f.read())
            
            # Add timestamps
            state['metadata']['updated_at'] = datetime.now().isoformat()
            
            # Write the state
            with open(self.target_path, 'w', encoding='utf-8') as f:
                f.write("/**\n * Auto-generated multi-agent communication file\n * DO NOT EDIT MANUALLY\n */\n\n")
                f.write("module.exports = ")
                json.dump(state, f, indent=2, default=str)
                f.write(";\n")
            
            logger.info(f"State written successfully to {self.target_path}")
            return True
        except Exception as e:
            logger.error(f"Error writing state: {e}")
            return False
    
    def update_phase(self, phase: str, status: str, data: Dict[str, Any] = None) -> bool:
        """Update the current phase and status"""
        try:
            state = self.read_state()
            state['phase'] = phase
            state[phase]['status'] = status
            
            if data:
                state[phase].update(data)
            
            state[phase]['timestamp'] = datetime.now().isoformat()
            
            return self.write_state(state)
        except Exception as e:
            logger.error(f"Error updating phase: {e}")
            return False
    
    def add_trace_log(self, phase: str, agent: str, event: str, data: Dict[str, Any] = None) -> bool:
        """Add a trace log entry for an agent"""
        try:
            state = self.read_state()
            
            trace_entry = {
                "timestamp": datetime.now().isoformat(),
                "agent": agent,
                "event": event,
                "data": data or {}
            }
            
            if phase == "global":
                state['global_trace'].append(trace_entry)
            else:
                state[phase]['trace_logs'].append(trace_entry)
            
            state['metadata']['phase_sequence'].append({
                "phase": phase,
                "agent": agent,
                "event": event,
                "timestamp": trace_entry['timestamp']
            })
            
            return self.write_state(state)
        except Exception as e:
            logger.error(f"Error adding trace log: {e}")
            return False
    
    def save_agent_output(self, phase: str, key: str, data: Any) -> bool:
        """Save agent output data to the target file"""
        try:
            state = self.read_state()
            state[phase][key] = data
            return self.write_state(state)
        except Exception as e:
            logger.error(f"Error saving agent output: {e}")
            return False
    
    def get_agent_input(self, phase: str, key: str) -> Any:
        """Retrieve input data for an agent from a previous phase"""
        try:
            state = self.read_state()
            return state[phase].get(key)
        except Exception as e:
            logger.error(f"Error getting agent input: {e}")
            return None
    
    def initialize_workflow(self, workflow_id: str, user_id: str, conversation_id: str, 
                           request_id: str, user_input: str) -> bool:
        """Initialize a new workflow"""
        try:
            state = self._get_default_state()
            state['workflow_id'] = workflow_id
            state['metadata']['user_id'] = user_id
            state['metadata']['conversation_id'] = conversation_id
            state['metadata']['request_id'] = request_id
            state['metadata']['created_at'] = datetime.now().isoformat()
            state['intake_validation']['user_input'] = user_input
            
            return self.write_state(state)
        except Exception as e:
            logger.error(f"Error initializing workflow: {e}")
            return False
    
    def cleanup(self, reason: str = "normal_completion") -> Dict[str, Any]:
        """Clean up the target.js file after workflow completion"""
        cleanup_log = {
            "status": "success",
            "files_deleted": [],
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            if self.target_path.exists():
                # Save cleanup log before deletion
                with open(self.target_path, 'r') as f:
                    final_state = json.load(f)
                
                os.remove(self.target_path)
                cleanup_log['files_deleted'].append(str(self.target_path))
                logger.info(f"Successfully deleted {self.target_path}")
                
                # Optionally remove backup
                if os.path.exists(self.backup_path):
                    os.remove(self.backup_path)
                    cleanup_log['files_deleted'].append(self.backup_path)
                    logger.info(f"Successfully deleted {self.backup_path}")
            
            return cleanup_log
        except Exception as e:
            cleanup_log['status'] = 'failed'
            cleanup_log['error'] = str(e)
            logger.error(f"Error during cleanup: {e}")
            return cleanup_log
    
    def get_workflow_summary(self) -> Dict[str, Any]:
        """Get a summary of the entire workflow"""
        try:
            state = self.read_state()
            return {
                "workflow_id": state.get('workflow_id'),
                "current_phase": state.get('phase'),
                "metadata": state.get('metadata', {}),
                "phase_statuses": {
                    "intake_validation": state['intake_validation'].get('status'),
                    "research_pricing": state['research_pricing'].get('status'),
                    "writing": state['writing'].get('status')
                },
                "global_trace_count": len(state.get('global_trace', [])),
                "total_events": len(state.get('metadata', {}).get('phase_sequence', []))
            }
        except Exception as e:
            logger.error(f"Error getting workflow summary: {e}")
            return {}
    
    def _get_default_state(self) -> Dict[str, Any]:
        """Get the default workflow state"""
        return {
            "workflow_id": "",
            "phase": "intake_validation",
            "timestamp": None,
            "intake_validation": {
                "status": "pending",
                "user_input": "",
                "validation_results": {
                    "is_valid": False,
                    "missing_fields": [],
                    "concerns": []
                },
                "initial_plan": {},
                "user_clarifications_needed": [],
                "hitl_response": None,
                "timestamp": None,
                "trace_logs": []
            },
            "research_pricing": {
                "status": "pending",
                "plan_from_intake": {},
                "research_results": {},
                "pricing_data": {},
                "recommendations": [],
                "issues_found": [],
                "timestamp": None,
                "trace_logs": []
            },
            "writing": {
                "status": "pending",
                "research_data": {},
                "final_output": "",
                "formatting_applied": [],
                "timestamp": None,
                "trace_logs": []
            },
            "global_trace": [],
            "metadata": {
                "created_at": None,
                "updated_at": None,
                "user_id": "",
                "conversation_id": "",
                "request_id": "",
                "phase_sequence": []
            }
        }


class RedisCommunicationManager:
    """Redis-backed communication manager. Stores full workflow JSON under a single key.

    Usage: provide `redis_url` or ensure `redis` client can connect to default host.
    """

    def __init__(self, redis_url: str = None, key: str = None):
        try:
            import redis
        except Exception as e:
            raise RuntimeError("redis package is required for RedisCommunicationManager") from e

        self.redis = redis.from_url(redis_url) if redis_url else redis.Redis()
        # key is the redis key used to store the workflow state. If not provided
        # the instance will create/expect 'workflow:default'
        self.key = key or "workflow:default"

    def read_state(self) -> Dict[str, Any]:
        try:
            raw = self.redis.get(self.key)
            if not raw:
                return FileCommunicationManager()._get_default_state()
            return json.loads(raw)
        except Exception:
            return FileCommunicationManager()._get_default_state()

    def write_state(self, state: Dict[str, Any]) -> bool:
        try:
            state['metadata']['updated_at'] = datetime.now().isoformat()
            payload = json.dumps(state, default=str)
            # Atomic set
            self.redis.set(self.key, payload)
            return True
        except Exception:
            return False

    def update_phase(self, phase: str, status: str, data: Dict[str, Any] = None) -> bool:
        state = self.read_state()
        state['phase'] = phase
        state[phase]['status'] = status
        if data:
            state[phase].update(data)
        state[phase]['timestamp'] = datetime.now().isoformat()
        return self.write_state(state)

    def add_trace_log(self, phase: str, agent: str, event: str, data: Dict[str, Any] = None) -> bool:
        state = self.read_state()
        trace_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "event": event,
            "data": data or {}
        }
        if phase == "global":
            state['global_trace'].append(trace_entry)
        else:
            state[phase]['trace_logs'].append(trace_entry)

        state['metadata']['phase_sequence'].append({
            "phase": phase,
            "agent": agent,
            "event": event,
            "timestamp": trace_entry['timestamp']
        })

        return self.write_state(state)

    def save_agent_output(self, phase: str, key: str, data: Any) -> bool:
        state = self.read_state()
        state[phase][key] = data
        return self.write_state(state)

    def get_agent_input(self, phase: str, key: str) -> Any:
        state = self.read_state()
        return state[phase].get(key)

    def initialize_workflow(self, workflow_id: str, user_id: str, conversation_id: str,
                           request_id: str, user_input: str) -> bool:
        state = FileCommunicationManager()._get_default_state()
        state['workflow_id'] = workflow_id
        state['metadata']['user_id'] = user_id
        state['metadata']['conversation_id'] = conversation_id
        state['metadata']['request_id'] = request_id
        state['metadata']['created_at'] = datetime.now().isoformat()
        state['intake_validation']['user_input'] = user_input
        return self.write_state(state)

    def cleanup(self, reason: str = "normal_completion") -> Dict[str, Any]:
        cleanup_log = {"status": "success", "files_deleted": [], "reason": reason,
                       "timestamp": datetime.now().isoformat()}
        try:
            self.redis.delete(self.key)
            cleanup_log['files_deleted'].append(self.key)
            return cleanup_log
        except Exception as e:
            cleanup_log['status'] = 'failed'
            cleanup_log['error'] = str(e)
            return cleanup_log

    def get_workflow_summary(self) -> Dict[str, Any]:
        state = self.read_state()
        return {
            "workflow_id": state.get('workflow_id'),
            "current_phase": state.get('phase'),
            "metadata": state.get('metadata', {}),
            "phase_statuses": {
                "intake_validation": state['intake_validation'].get('status'),
                "research_pricing": state['research_pricing'].get('status'),
                "writing": state['writing'].get('status')
            },
            "global_trace_count": len(state.get('global_trace', [])),
            "total_events": len(state.get('metadata', {}).get('phase_sequence', []))
        }


class SQLiteCommunicationManager:
    """SQLite-backed communication manager (file-based DB). Uses a single table
    to store workflow state as JSON. Good fallback for development without Redis.
    """

    def __init__(self, db_path: str = None, key: str = None):
        import sqlite3
        self.db_path = db_path or str(Path(__file__).parent.parent / "workflow_state.db")
        self.key = key or "default"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cur = self._conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            key TEXT PRIMARY KEY,
            state TEXT NOT NULL
        )
        """)
        self._conn.commit()

    def read_state(self) -> Dict[str, Any]:
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT state FROM workflows WHERE key = ?", (self.key,))
            row = cur.fetchone()
            if not row:
                return FileCommunicationManager()._get_default_state()
            return json.loads(row[0])
        except Exception:
            return FileCommunicationManager()._get_default_state()

    def write_state(self, state: Dict[str, Any]) -> bool:
        try:
            state['metadata']['updated_at'] = datetime.now().isoformat()
            payload = json.dumps(state, default=str)
            cur = self._conn.cursor()
            cur.execute("INSERT OR REPLACE INTO workflows(key, state) VALUES (?, ?)", (self.key, payload))
            self._conn.commit()
            return True
        except Exception:
            return False

    def update_phase(self, phase: str, status: str, data: Dict[str, Any] = None) -> bool:
        state = self.read_state()
        state['phase'] = phase
        state[phase]['status'] = status
        if data:
            state[phase].update(data)
        state[phase]['timestamp'] = datetime.now().isoformat()
        return self.write_state(state)

    def add_trace_log(self, phase: str, agent: str, event: str, data: Dict[str, Any] = None) -> bool:
        state = self.read_state()
        trace_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "event": event,
            "data": data or {}
        }
        if phase == "global":
            state['global_trace'].append(trace_entry)
        else:
            state[phase]['trace_logs'].append(trace_entry)

        state['metadata']['phase_sequence'].append({
            "phase": phase,
            "agent": agent,
            "event": event,
            "timestamp": trace_entry['timestamp']
        })

        return self.write_state(state)

    def save_agent_output(self, phase: str, key: str, data: Any) -> bool:
        state = self.read_state()
        state[phase][key] = data
        return self.write_state(state)

    def get_agent_input(self, phase: str, key: str) -> Any:
        state = self.read_state()
        return state[phase].get(key)

    def initialize_workflow(self, workflow_id: str, user_id: str, conversation_id: str,
                           request_id: str, user_input: str) -> bool:
        state = FileCommunicationManager()._get_default_state()
        state['workflow_id'] = workflow_id
        state['metadata']['user_id'] = user_id
        state['metadata']['conversation_id'] = conversation_id
        state['metadata']['request_id'] = request_id
        state['metadata']['created_at'] = datetime.now().isoformat()
        state['intake_validation']['user_input'] = user_input
        return self.write_state(state)

    def cleanup(self, reason: str = "normal_completion") -> Dict[str, Any]:
        cleanup_log = {"status": "success", "files_deleted": [], "reason": reason,
                       "timestamp": datetime.now().isoformat()}
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM workflows WHERE key = ?", (self.key,))
            self._conn.commit()
            cleanup_log['files_deleted'].append(self.key)
            return cleanup_log
        except Exception as e:
            cleanup_log['status'] = 'failed'
            cleanup_log['error'] = str(e)
            return cleanup_log

    def get_workflow_summary(self) -> Dict[str, Any]:
        state = self.read_state()
        return {
            "workflow_id": state.get('workflow_id'),
            "current_phase": state.get('phase'),
            "metadata": state.get('metadata', {}),
            "phase_statuses": {
                "intake_validation": state['intake_validation'].get('status'),
                "research_pricing": state['research_pricing'].get('status'),
                "writing": state['writing'].get('status')
            },
            "global_trace_count": len(state.get('global_trace', [])),
            "total_events": len(state.get('metadata', {}).get('phase_sequence', []))
        }


class CommunicationManager:
    """Wrapper factory that selects the appropriate backend implementation.

    Parameters:
        backend: 'redis'|'sqlite'|'file' or None. If None, environment var
                 COMM_BACKEND is consulted. Defaults to 'file'.
        **kwargs: forwarded to backend constructor (e.g., redis_url, db_path, key)
    """

    def __init__(self, backend: str = None, **kwargs):
        backend = backend or os.environ.get('COMM_BACKEND', 'file')
        backend = backend.lower()
        if backend == 'redis':
            try:
                # Prefer explicit kwarg, then standard env vars
                redis_url = kwargs.get('redis_url') or os.environ.get('REDIS_URL') or os.environ.get('COMM_REDIS_URL')
                self._impl = RedisCommunicationManager(redis_url, kwargs.get('key'))
            except Exception as e:
                logger.warning(f"Redis backend failed to initialize: {e}. Falling back to SQLite.")
                self._impl = SQLiteCommunicationManager(kwargs.get('db_path'), kwargs.get('key'))
        elif backend == 'sqlite':
            self._impl = SQLiteCommunicationManager(kwargs.get('db_path'), kwargs.get('key'))
        else:
            # file
            self._impl = FileCommunicationManager(kwargs.get('target_file_path'))

    def __getattr__(self, name):
        return getattr(self._impl, name)


class TraceRecorder:
    """Records and manages trace logs throughout agent execution"""
    
    def __init__(self, comm_manager: CommunicationManager):
        self.comm_manager = comm_manager
        self.start_time = time.time()
        self.events = []
    
    def record_event(self, phase: str, agent: str, event_type: str, 
                    data: Dict[str, Any] = None, metadata: Dict[str, Any] = None) -> None:
        """Record a single event in the trace"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_ms": (time.time() - self.start_time) * 1000,
            "phase": phase,
            "agent": agent,
            "event_type": event_type,
            "data": data or {},
            "metadata": metadata or {}
        }
        
        self.events.append(event)
        self.comm_manager.add_trace_log(phase, agent, event_type, data)
        
        logger.info(f"[{phase}] {agent}: {event_type} - {json.dumps(data or {})}")
    
    def record_tool_call(self, phase: str, agent: str, tool_name: str, 
                        tool_args: Dict[str, Any], result: Any, 
                        duration_ms: float, cache_hit: bool = False) -> None:
        """Record a tool call"""
        self.record_event(
            phase=phase,
            agent=agent,
            event_type="tool_call",
            data={
                "tool_name": tool_name,
                "args": str(tool_args)[:200],
                "result_preview": str(result)[:200] if result else None,
                "cache_hit": cache_hit
            },
            metadata={"duration_ms": duration_ms}
        )
    
    def record_error(self, phase: str, agent: str, error: str, 
                    error_details: str = None) -> None:
        """Record an error event"""
        self.record_event(
            phase=phase,
            agent=agent,
            event_type="error",
            data={
                "error": error,
                "details": error_details or ""
            }
        )
    
    def record_decision(self, phase: str, agent: str, decision: str, 
                       reasoning: str, alternatives: List[str] = None) -> None:
        """Record a decision made by an agent"""
        self.record_event(
            phase=phase,
            agent=agent,
            event_type="decision",
            data={
                "decision": decision,
                "reasoning": reasoning,
                "alternatives": alternatives or []
            }
        )
    
    def get_trace_summary(self) -> Dict[str, Any]:
        """Get a summary of all recorded events"""
        return {
            "total_events": len(self.events),
            "total_duration_ms": (time.time() - self.start_time) * 1000,
            "events_by_agent": self._group_by_agent(),
            "events_by_type": self._group_by_type(),
            "events": self.events
        }
    
    def _group_by_agent(self) -> Dict[str, int]:
        """Group events by agent"""
        grouped = {}
        for event in self.events:
            agent = event['agent']
            grouped[agent] = grouped.get(agent, 0) + 1
        return grouped
    
    def _group_by_type(self) -> Dict[str, int]:
        """Group events by event type"""
        grouped = {}
        for event in self.events:
            event_type = event['event_type']
            grouped[event_type] = grouped.get(event_type, 0) + 1
        return grouped


class WorkflowOrchestrator:
    """Orchestrates the multi-agent workflow"""
    
    def __init__(self, comm_manager: CommunicationManager, trace_recorder: TraceRecorder):
        self.comm_manager = comm_manager
        self.trace_recorder = trace_recorder
    
    def initialize_workflow(self, workflow_id: str, user_id: str, conversation_id: str,
                           request_id: str, user_input: str) -> bool:
        """Initialize a new workflow"""
        success = self.comm_manager.initialize_workflow(
            workflow_id, user_id, conversation_id, request_id, user_input
        )
        
        if success:
            self.trace_recorder.record_event(
                phase="global",
                agent="orchestrator",
                event_type="workflow_initialized",
                data={
                    "workflow_id": workflow_id,
                    "user_id": user_id,
                    "conversation_id": conversation_id
                }
            )
        
        return success
    
    def move_to_next_phase(self, current_phase: str, next_phase: str, 
                          phase_data: Dict[str, Any]) -> bool:
        """Move workflow to the next phase"""
        success = self.comm_manager.update_phase(next_phase, "in_progress", phase_data)
        
        if success:
            self.trace_recorder.record_decision(
                phase="global",
                agent="orchestrator",
                decision=f"move_to_phase_{next_phase}",
                reasoning=f"Transitioning from {current_phase} to {next_phase}",
                alternatives=[f"stay_in_{current_phase}", "terminate_workflow"]
            )
        
        return success
    
    def complete_workflow(self, final_output: str) -> Dict[str, Any]:
        """Complete the workflow and cleanup"""
        # Mark writing phase as complete
        self.comm_manager.update_phase("writing", "completed", {
            "final_output": final_output
        })
        
        self.trace_recorder.record_event(
            phase="global",
            agent="orchestrator",
            event_type="workflow_completed",
            data={"output_length": len(final_output)}
        )
        
        # Cleanup target.js
        cleanup_log = self.comm_manager.cleanup(reason="workflow_completion")
        
        return {
            "status": "success",
            "final_output": final_output,
            "cleanup": cleanup_log,
            "trace_summary": self.trace_recorder.get_trace_summary(),
            "workflow_summary": self.comm_manager.get_workflow_summary()
        }
