# Multi-Agent Workflow Architecture & Data Flow

## 🏗️ System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│                     (API / Controller)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ user_input
                            │ user_id
                            │ conversation_id
                            │ custom_prompts (optional)
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    MultiAgentEngine                             │
│  (Main Orchestration Point - process_with_multi_agents)         │
└──────────────────────────┬────────────────────────────────────────┘
                           │
                ┌──────────┼──────────┐
                │          │          │
                ↓          ↓          ↓
    ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │ PHASE 1         │ │ PHASE 2          │ │ PHASE 3          │
    │ INTAKE          │ │ RESEARCH &       │ │ WRITING          │
    │ VALIDATOR       │ │ PRICING          │ │ AGENT            │
    │                 │ │                  │ │                  │
    │ - Validates     │ │ - Conducts       │ │ - Synthesizes    │
    │ - Extracts      │ │   research       │ │ - Formats output │
    │ - Plans         │ │ - Gathers        │ │ - Cleans up      │
    │ - Identifies    │ │   pricing        │ │                  │
    │   missing info  │ │ - Identifies     │ │ [CLEANUP: deletes│
    │                 │ │   issues         │ │  target.js here] │
    └────────┬────────┘ └────────┬─────────┘ └────────┬─────────┘
             │                   │                    │
             └───────────────────┼────────────────────┘
                                 │
                    ┌────────────v──────────────┐
                    │  CommunicationManager     │
                    │                           │
                    │  • Read state             │
                    │  • Write state            │
                    │  • Update phase           │
                    │  • Add trace logs         │
                    │  • Initialize workflow    │
                    │  • Cleanup files          │
                    └────────────┬──────────────┘
                                 │
                                 ↓
                    ┌────────────────────────┐
                    │   target.js (JSON)     │
                    │ Communication Hub      │
                    │                        │
                    │ {                      │
                    │  workflow_id: "...",   │
                    │  phase: "current",     │
                    │  intake_validation: {  │
                    │    status: "...",      │
                    │    results: { ... },   │
                    │    trace_logs: [...]   │
                    │  },                    │
                    │  research_pricing: {   │
                    │    status: "...",      │
                    │    results: { ... },   │
                    │    trace_logs: [...]   │
                    │  },                    │
                    │  writing: {            │
                    │    status: "...",      │
                    │    output: "...",      │
                    │    trace_logs: [...]   │
                    │  },                    │
                    │  global_trace: [ ... ] │
                    │ }                      │
                    └────────────────────────┘
                                 │
                    ┌────────────v──────────────┐
                    │   TraceRecorder           │
                    │   (Audit & Logging)       │
                    │                           │
                    │  • Record events          │
                    │  • Record tool calls      │
                    │  • Record errors          │
                    │  • Record decisions       │
                    │  • Generate summaries     │
                    └────────────────────────────┘
                                 │
                                 ↓
                    ┌────────────────────────────┐
                    │  Final Result              │
                    │                            │
                    │  {                         │
                    │    status: "success",      │
                    │    final_output: "...",    │
                    │    phases: { ... },        │
                    │    trace: { ... },         │
                    │    workflow_summary: {...} │
                    │  }                         │
                    └────────────────────────────┘
                                 │
                                 ↓
                    ┌────────────────────────────┐
                    │   User Receives Result      │
                    │   + Complete Trace Logs     │
                    └────────────────────────────┘
```

---

## 📊 Detailed Data Flow

### Flow 1: Input Processing

```
User Input
    ↓
[VALIDATION] Is input valid?
    ├─ YES → Continue to Phase 1
    ├─ NEEDS_CLARIFICATION → Ask questions
    └─ NO → Return error

Clarifications collected
    ↓
Continue to Phase 1 (with updated input)
```

### Flow 2: Phase 1 - Intake Validation

```
INPUT: raw user_input
    ↓
1. Initialize Communication
   ├─ Create target.js
   ├─ Initialize workflow state
   └─ Start trace recorder
    ↓
2. Parse User Input
   ├─ Extract requirements
   ├─ Identify missing fields
   ├─ Check for ambiguities
   └─ Calculate confidence
    ↓
3. Decision Tree
   ├─ If confidence < threshold
   │  ├─ Generate clarification questions
   │  └─ Save to target.js
   ├─ If confidence >= threshold
   │  ├─ Create initial plan
   │  ├─ Mark as validated
   │  └─ Save to target.js
   └─ If invalid
      └─ Return error
    ↓
4. Output
   ├─ validation_results
   ├─ initial_plan
   ├─ clarification_questions
   ├─ trace_logs
   └─ Save all to target.js
    ↓
RETURN to Phase 2 OR Continue if needs_clarification
```

### Flow 3: Phase 2 - Research & Pricing

```
INPUT: initial_plan from Phase 1 (via target.js)
    ↓
1. Load Communication
   ├─ Read target.js
   ├─ Extract Phase 1 results
   └─ Continue trace recorder
    ↓
2. Research Strategy
   ├─ Identify research areas
   ├─ Check cache for existing data
   ├─ Plan tool calls
   └─ Estimate API usage
    ↓
3. Execute Research
   ├─ Call tools strategically
   ├─ Track API calls
   ├─ Log cache hits
   ├─ Handle errors gracefully
   └─ Record all events in trace
    ↓
4. Analyze Results
   ├─ Cross-reference sources
   ├─ Identify pricing options
   ├─ Detect issues
   ├─ Rate confidence
   └─ Generate recommendations
    ↓
5. Output
   ├─ research_results
   ├─ pricing_data
   ├─ issues_identified
   ├─ recommendations
   ├─ tool_usage_log
   ├─ trace_logs
   └─ Update target.js
    ↓
RETURN to Phase 3
```

### Flow 4: Phase 3 - Writing & Cleanup

```
INPUT: research_data from Phase 2 (via target.js)
    ↓
1. Load Communication
   ├─ Read target.js
   ├─ Extract all phase data
   └─ Continue trace recorder
    ↓
2. Synthesize Output
   ├─ Combine all findings
   ├─ Prioritize key information
   ├─ Organize by sections
   └─ Apply formatting
    ↓
3. Write Final Output
   ├─ Format as markdown/HTML/JSON/text
   ├─ Include pricing summary
   ├─ Add recommendations
   ├─ Include disclaimers
   ├─ Check quality metrics
   └─ Record all events in trace
    ↓
4. Cleanup Phase
   ├─ Verify output complete
   ├─ Record cleanup start
   ├─ Delete target.js
   ├─ Delete backup files
   ├─ Log cleanup details
   └─ Record cleanup completion
    ↓
5. Output
   ├─ final_output
   ├─ output_metadata
   ├─ cleanup_log
   ├─ trace_logs (final)
   └─ Complete result
    ↓
RETURN: Final Result to User
```

---

## 🔄 State Machine Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    WORKFLOW STATE MACHINE                   │
└─────────────────────────────────────────────────────────────┘

                          START
                            │
                            ↓
            ┌───────────────────────────┐
            │  INTAKE_VALIDATION:       │
            │  pending                  │
            └─────────┬─────────────────┘
                      │
                      ├─→ [Validation] ──→ needs_clarification
                      │                      │
                      │                      ↓ (user provides clarifications)
                      │                     [Ask for input]
                      │                      │
                      │    ┌─────────────────┘
                      │    │
                      ├─→ [Validation] ──→ invalid ──→ ERROR
                      │
                      ├─→ [Validation] ──→ validated ──→ status = in_progress
                      │
                      ↓
            ┌───────────────────────────┐
            │  RESEARCH_PRICING:        │
            │  in_progress              │
            └─────────┬─────────────────┘
                      │
                      ├─→ [Research] ──→ error ──→ ERROR or PARTIAL
                      │
                      ├─→ [Research] ──→ success ──→ status = in_progress
                      │
                      ↓
            ┌───────────────────────────┐
            │  WRITING:                 │
            │  in_progress              │
            └─────────┬─────────────────┘
                      │
                      ├─→ [Write] ──→ error ──→ ERROR
                      │
                      ├─→ [Write] ──→ success ──→ status = completed
                      │
                      ├─→ [Cleanup] ──→ Delete target.js
                      │
                      ↓
            ┌───────────────────────────┐
            │  COMPLETED                │
            │  Final result returned    │
            └───────────────────────────┘
                      │
                      ↓
                      END
```

---

## 📈 Data Structure Hierarchy

```
MultiAgentEngine.process_with_multi_agents()
    ↓
Result: {
    status: "success" | "error" | "needs_clarification",
    
    if success:
        ├─ final_output: str (main deliverable)
        │
        ├─ phases: {
        │   ├─ intake_validation: {
        │   │   ├─ status: "completed"
        │   │   ├─ validation: {
        │   │   │   ├─ status: "validated"
        │   │   │   ├─ confidence: 85
        │   │   │   ├─ extracted_requirements: {...}
        │   │   │   ├─ missing_information: [...]
        │   │   │   ├─ concerns: [...]
        │   │   │   ├─ initial_plan: {...}
        │   │   │   └─ reasoning: "..."
        │   │   ├─ plan: {...}
        │   │   └─ duration_ms: 3245
        │   │
        │   ├─ research_pricing: {
        │   │   ├─ status: "completed"
        │   │   ├─ research: {
        │   │   │   ├─ status: "research_complete"
        │   │   │   ├─ research_results: {...}
        │   │   │   ├─ pricing_summary: {...}
        │   │   │   ├─ issues_identified: [...]
        │   │   │   ├─ recommendations: [...]
        │   │   │   └─ tool_usage_log: [...]
        │   │   ├─ duration_ms: 15234
        │   │   └─ api_calls: 8
        │   │
        │   └─ writing: {
        │       ├─ status: "completed"
        │       ├─ output_metadata: {...}
        │       ├─ cleanup: {
        │       │   ├─ status: "success"
        │       │   ├─ files_deleted: [...]
        │       │   └─ timestamp: "..."
        │       └─ duration_ms: 5678
        │
        ├─ trace: {
        │   ├─ total_events: 52
        │   ├─ total_duration_ms: 24157
        │   ├─ events_by_agent: {
        │   │   ├─ intake_validator: 12
        │   │   ├─ research_pricing: 35
        │   │   └─ writer: 5
        │   ├─ events_by_type: {
        │   │   ├─ tool_call: 20
        │   │   ├─ decision: 8
        │   │   ├─ error: 0
        │   │   ├─ llm_invoke: 3
        │   │   └─ ... (40+ types)
        │   └─ events: [
        │       {
        │           timestamp: "2024-05-27T...",
        │           elapsed_ms: 1234,
        │           phase: "research_pricing",
        │           agent: "research_pricing",
        │           event_type: "tool_call",
        │           data: {...},
        │           metadata: {...}
        │       },
        │       ... (more events)
        │   ]
        │
        └─ workflow_summary: {
            ├─ workflow_id: "uuid-xxx"
            ├─ current_phase: "writing"
            ├─ metadata: {...}
            ├─ phase_statuses: {
            │   ├─ intake_validation: "completed"
            │   ├─ research_pricing: "completed"
            │   └─ writing: "completed"
            ├─ global_trace_count: 52
            └─ total_events: 52
    
    if error:
        ├─ phase: "phase_name"
        ├─ error: "error message"
        ├─ error_traceback: "..."
        ├─ trace: {...}  (partial)
        └─ request_id: "..."
    
    if needs_clarification:
        ├─ phase: "intake_validation"
        ├─ clarification_questions: [
        │   "Question 1?",
        │   "Question 2?",
        │   "Question 3?"
        │ ]
        └─ trace: {...}
}
```

---

## 🔀 Communication Flow Between Phases

```
Phase 1 (Intake Validator)
    │
    ├─ Validates input
    ├─ Creates plan
    │
    └─→ SAVE TO target.js
        {
            intake_validation: {
                status: "completed",
                validation_results: {...},
                initial_plan: {...}
            }
        }
        
        ↓
        
Phase 2 (Research & Pricing) READS target.js
    │
    ├─ Gets: initial_plan
    ├─ Gets: extracted_requirements
    │
    ├─ Conducts research
    ├─ Gathers pricing
    │
    └─→ UPDATE target.js
        {
            research_pricing: {
                status: "completed",
                plan_from_intake: {...},
                research_results: {...},
                pricing_data: {...}
            }
        }
        
        ↓
        
Phase 3 (Writer) READS target.js
    │
    ├─ Gets: research_results
    ├─ Gets: pricing_data
    ├─ Gets: recommendations
    ├─ Gets: issues_found
    │
    ├─ Synthesizes output
    ├─ Formats beautifully
    │
    └─→ DELETE target.js
        (Cleanup completed)
        
        ↓
        
Final Result to User
    + Complete trace logs
    + Workflow summary
```

---

## 🎯 Event Tracing Timeline

```
Workflow Start: T=0ms
    │
    ├─ T=10ms   : workflow_initialized
    ├─ T=50ms   : intake_validator agent started
    ├─ T=100ms  : llm_invoked (Phase 1)
    ├─ T=3500ms : llm_response_received
    ├─ T=3510ms : validation_completed
    ├─ T=3520ms : research_pricing agent started
    ├─ T=3600ms : llm_invoked (Phase 2)
    ├─ T=5000ms : tool_called (flight_search)
    ├─ T=8500ms : tool_success
    ├─ T=9000ms : tool_called (hotel_search)
    ├─ T=12000ms: tool_success
    ├─ T=16500ms: llm_response_received
    ├─ T=16510ms: research_completed
    ├─ T=16520ms: writer agent started
    ├─ T=16600ms: llm_invoked (Phase 3)
    ├─ T=20000ms: llm_response_received
    ├─ T=20010ms: output_generated
    ├─ T=20050ms: cleanup_started
    ├─ T=20100ms: cleanup_completed (target.js deleted)
    ├─ T=20110ms: writing_completed
    ├─ T=20120ms: workflow_completed
    │
    └─ T=20150ms: Final Result Returned

Total Duration: 20.15 seconds
Total Events: 52
```

---

## 🔐 Error Handling Flow

```
Each Phase:
    │
    ├─ Try to execute
    │   ├─ SUCCESS → Mark as completed, continue to next phase
    │   │
    │   ├─ ERROR → Record error in trace
    │   │   ├─ If ignorable → Try to recover
    │   │   ├─ If critical → Mark phase as failed
    │   │   └─ Return error to user
    │   │
    │   └─ PARTIAL → Record partial results
    │       ├─ Continue to next phase with partial data
    │       └─ Flag issues for user awareness
    │
    └─ ALL errors recorded in trace for debugging
```

---

## 💾 Target.js Lifecycle

```
Phase 1 Start
    │
    └─→ target.js CREATED
        {
            workflow_id: "xyz",
            phase: "intake_validation",
            intake_validation: { status: "in_progress" }
        }
        
        ↓
        
Phase 1 Complete
    │
    └─→ target.js UPDATED
        {
            intake_validation: {
                status: "completed",
                validation_results: {...},
                initial_plan: {...},
                trace_logs: [...]
            }
        }
        
        ↓
        
Phase 2 Start & Complete
    │
    └─→ target.js UPDATED (appended)
        {
            research_pricing: {
                status: "completed",
                research_results: {...},
                trace_logs: [...]
            }
        }
        
        ↓
        
Phase 3 Start & Complete
    │
    └─→ target.js UPDATED (final)
        {
            writing: {
                status: "completed",
                final_output: "...",
                trace_logs: [...]
            }
        }
        
        ↓
        
Phase 3 Cleanup
    │
    ├─→ Backup created
    ├─→ target.js DELETED
    ├─→ Cleanup logged
    └─→ Result returned to user
```

---

This complete architecture documentation shows exactly how data flows through the system, how agents communicate, and how the entire workflow is orchestrated and traced.
