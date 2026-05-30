# Multi-Agent Workflow System - Complete Documentation

## Overview

The Multi-Agent Workflow System implements a three-phase orchestrated workflow where specialized agents work together to process user queries:

1. **Phase 1: Intake Validator** - Validates input and creates initial plans
2. **Phase 2: Research & Pricing** - Conducts research and gathers pricing
3. **Phase 3: Writer** - Synthesizes findings and produces final output

Agents communicate via a shared `target.js` file and all activities are traced and logged.

---

## Architecture

### Core Components

```
agent_file/
├── agent/
│   ├── agentic_workflow.py          # Main orchestration (updated)
│   └── multi_agents.py              # Three agent implementations
├── utils/
│   ├── communication_manager.py     # Inter-agent communication
│   ├── multi_agent_config.py        # Configuration management
│   └── ...
├── prompt_library/
│   ├── multi_agent_prompts.py       # Phase-specific prompts
│   └── ...
└── target.js                         # Communication hub (JSON file)
```

### Data Flow

```
User Input
    ↓
Phase 1: Intake Validator
    ├─ Validates input
    ├─ Extracts requirements
    ├─ Creates initial plan
    └─ Saves to target.js
    ↓
Phase 2: Research & Pricing
    ├─ Reads plan from target.js
    ├─ Conducts research
    ├─ Gathers pricing
    └─ Updates target.js
    ↓
Phase 3: Writer
    ├─ Reads research from target.js
    ├─ Synthesizes output
    ├─ Deletes target.js
    └─ Returns final output
    ↓
Final Output + Trace Logs
```

---

## Usage Examples

### Basic Usage

```python
from agent_file.agent.agentic_workflow import AgentRunner, MultiAgentEngine
from agent_file.utils.model_loader import load_travel_planning_llm

# Initialize
router = ModelRouter(config)  # Your model router
agent_runner = AgentRunner(router)
multi_engine = MultiAgentEngine(agent_runner)

# Process user input through all 3 phases
result = multi_engine.process_with_multi_agents(
    user_input="I want to plan a trip to Japan for 2 weeks in April. Budget is around $3000",
    user_id="user_123",
    conversation_id="conv_123"
)

# Result structure
if result["status"] == "success":
    print(result["final_output"])
    print(f"Trace events: {len(result['trace']['events'])}")
    print(f"Total time: {result['trace']['total_duration_ms']}ms")
```

### With Custom Prompts

```python
# Define custom prompts for each phase
custom_prompts = {
    "intake_validation": "Be very strict - validate everything strictly",
    "research_pricing": "Focus on budget-friendly options",
    "writing": "Use executive summary format"
}

result = multi_engine.process_with_multi_agents(
    user_input="...",
    user_id="user_123",
    custom_prompts=custom_prompts
)
```

### With Configuration

```python
from agent_file.utils.multi_agent_config import (
    get_config_for_phase,
    update_config,
    get_custom_prompt_for_phase
)

# Modify configuration
update_config("research_pricing", "max_api_calls", 20)

# Get phase configuration
intake_config = get_config_for_phase("intake_validation")

# Get custom prompt variant
budget_focused = get_custom_prompt_for_phase(
    "research_pricing",
    "budget_focused"
)

result = multi_engine.process_with_multi_agents(
    user_input="...",
    user_id="user_123",
    custom_prompts={"research_pricing": budget_focused}
)
```

---

## Phase Details

### Phase 1: Intake Validation

**Responsibilities:**
- Validate input completeness
- Extract requirements
- Identify missing information
- Create initial plan
- Determine if clarification is needed

**Output Structure:**
```json
{
  "status": "validated | needs_clarification | invalid",
  "confidence": 75,
  "extracted_requirements": { ... },
  "missing_information": [...],
  "concerns": [...],
  "initial_plan": { ... },
  "clarification_questions": [...],
  "reasoning": "...",
  "trace_markers": { ... }
}
```

**Customization:**
- Override system prompt
- Adjust confidence threshold
- Control detail level

### Phase 2: Research & Pricing

**Responsibilities:**
- Execute smart research using tools
- Gather pricing and availability
- Cross-reference multiple sources
- Identify issues or gaps
- Track tool usage

**Output Structure:**
```json
{
  "status": "research_complete | partial_results | research_failed",
  "research_results": { ... },
  "pricing_summary": { ... },
  "issues_identified": [...],
  "recommendations": [...],
  "tool_usage_log": [...],
  "trace_markers": { ... }
}
```

**Customization:**
- Adjust API call limits
- Choose research strategy
- Focus on specific areas
- Control pricing presentation

### Phase 3: Writing

**Responsibilities:**
- Synthesize all research
- Create user-friendly output
- Apply professional formatting
- Include disclaimers
- Clean up temporary files

**Output Structure:**
```json
{
  "status": "writing_complete | writing_failed",
  "final_output": "...",
  "output_structure": [...],
  "formatting_applied": [...],
  "character_count": 5000,
  "quality_checks": { ... },
  "cleanup_log": { ... },
  "trace_markers": { ... }
}
```

**Customization:**
- Choose output format (markdown, HTML, plain text, JSON)
- Set tone (formal, professional, casual, technical)
- Control detail level (brief, moderate, detailed)
- Include/exclude sections

---

## Communication File (target.js)

The `target.js` file serves as the inter-agent communication hub:

```javascript
module.exports = {
  workflow_id: "uuid-xxx",
  phase: "current_phase",
  
  intake_validation: {
    status: "pending | in_progress | completed | failed",
    user_input: "...",
    validation_results: { ... },
    initial_plan: { ... },
    trace_logs: [...]
  },
  
  research_pricing: {
    status: "pending | in_progress | completed | failed",
    research_results: { ... },
    pricing_data: { ... },
    trace_logs: [...]
  },
  
  writing: {
    status: "pending | in_progress | completed | failed",
    final_output: "...",
    trace_logs: [...]
  },
  
  global_trace: [
    {
      timestamp: "2024-...",
      agent: "agent_name",
      event: "event_type",
      data: { ... }
    }
  ],
  
  metadata: {
    created_at: "...",
    user_id: "...",
    conversation_id: "...",
    phase_sequence: [...]
  }
};
```

**Key Features:**
- Agents read/write their phase data
- Global trace logs all events
- Timestamps track every action
- Metadata maintains context
- Automatically deleted after completion

---

## Tracing & Logging

### Trace Recording

All activities are automatically traced:

```python
trace_recorder.record_event(
    phase="intake_validation",
    agent="intake_validator",
    event_type="validation_started",
    data={"input_length": 150}
)

trace_recorder.record_tool_call(
    phase="research_pricing",
    agent="research_pricing",
    tool_name="flight_search",
    tool_args={"origin": "NYC", "destination": "Tokyo"},
    result={"flights": [...]},
    duration_ms=250,
    cache_hit=False
)

trace_recorder.record_decision(
    phase="intake_validation",
    agent="intake_validator",
    decision="needs_clarification",
    reasoning="Missing travel dates",
    alternatives=["validated", "invalid"]
)

trace_recorder.record_error(
    phase="research_pricing",
    agent="research_pricing",
    error="API timeout",
    error_details="Request took >60s"
)
```

### Trace Summary

```python
trace_summary = trace_recorder.get_trace_summary()
# Returns:
{
    "total_events": 45,
    "total_duration_ms": 5230,
    "events_by_agent": {
        "intake_validator": 12,
        "research_pricing": 28,
        "writer": 5
    },
    "events_by_type": {
        "tool_call": 20,
        "decision": 8,
        "error": 1,
        "llm_invoke": 3
    },
    "events": [...]
}
```

---

## Error Handling

### Error Scenarios

```python
# Phase fails
if result["status"] == "error":
    print(f"Phase: {result['phase']}")
    print(f"Error: {result['error']}")
    print(f"Trace: {result['trace']}")

# Needs clarification
if result["status"] == "needs_clarification":
    print("Questions to ask user:")
    for q in result["clarification_questions"]:
        print(f"  - {q}")

# Partial results
if result.get("phases", {}).get("research_pricing", {}).get("status") == "partial_results":
    print("Some research was incomplete")
```

### Recovery

```python
# Retry with better input
result = multi_engine.process_with_multi_agents(
    user_input="Updated input with clarifications",
    user_id="user_123",
    conversation_id="conv_123"  # Same conversation to maintain context
)
```

---

## Configuration

### Per-Phase Configuration

```python
from agent_file.utils.multi_agent_config import MULTI_AGENT_WORKFLOW_CONFIG

# Modify
MULTI_AGENT_WORKFLOW_CONFIG["phases"]["research_pricing"]["research_strategy"]["max_api_calls"] = 20

# Validate
from agent_file.utils.multi_agent_config import validate_config
if validate_config():
    print("Config is valid")
```

### Custom Prompts

```python
CUSTOM_PHASE_PROMPTS = {
    "intake_validation": {
        "budget_conscious": "User is budget-conscious, flag expensive options",
        "luxury": "User values quality over price",
        "eco_conscious": "User prioritizes sustainable options"
    },
    "research_pricing": {
        "local_focus": "Research local options first",
        "international": "Include international options"
    },
    "writing": {
        "technical": "Use technical terminology",
        "simple": "Explain everything in simple terms"
    }
}
```

---

## Performance Metrics

The system tracks:
- **Latency**: Time for each phase and component
- **Tool Usage**: API calls, cache hits, errors
- **Quality Metrics**: Confidence scores, completeness
- **Errors**: Failures, retries, fallbacks
- **Trace Events**: 45+ event types tracked

---

## Best Practices

### Input Design
```python
# ✅ Good
user_input = "Plan a 2-week trip to Japan in April for 2 people, budget $5000/person"

# ❌ Poor
user_input = "Plan trip"
```

### Custom Prompts
```python
# ✅ Good - specific and actionable
custom_prompts = {
    "research_pricing": "Find the top 3 options by price, quality, and availability"
}

# ❌ Poor - vague
custom_prompts = {
    "research_pricing": "Find good options"
}
```

### Error Handling
```python
# ✅ Good
result = multi_engine.process_with_multi_agents(...)
if result["status"] == "error":
    # Handle gracefully
    fallback = provide_fallback_response()
elif result["status"] == "needs_clarification":
    # Ask user
    clarified_input = ask_user_questions(result["clarification_questions"])
    result = multi_engine.process_with_multi_agents(clarified_input)

# ❌ Poor
result = multi_engine.process_with_multi_agents(...)
print(result["final_output"])  # May crash if error
```

---

## Integration with Existing Code

```python
# Old single-agent approach
travel_engine = TravelEngine(agent_runner)
response, pref, history, is_hitl = travel_engine.process_query(...)

# New multi-agent approach
multi_engine = MultiAgentEngine(agent_runner)
result = multi_engine.process_with_multi_agents(...)

# Can be used together
# Use TravelEngine for simpler queries
# Use MultiAgentEngine for complex queries requiring full orchestration
```

---

## Troubleshooting

### Phase Doesn't Complete
- Check trace logs for errors
- Verify LLM is responding
- Check network connectivity for tool calls
- Increase timeout in configuration

### Target.js File Issues
- Ensure write permissions to `agent_file/` directory
- Check disk space
- Verify JSON formatting
- Backup is created before each write

### Memory/Performance Issues
- Reduce max_api_calls
- Disable detailed tracing
- Clear backup files
- Use shorter conversation histories

### Quality Issues
- Adjust confidence thresholds
- Use different custom prompts
- Provide better input descriptions
- Review and improve validation rules

---

## Next Steps

1. **Integrate** with your existing API/controller
2. **Test** with sample queries
3. **Customize** prompts for your domain
4. **Monitor** trace logs for optimization
5. **Iterate** based on user feedback
