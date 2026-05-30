# Multi-Agent Workflow - Quick Reference Guide

## 🚀 Quick Start (5 minutes)

### Install & Initialize
```python
from agent_file.agent.agentic_workflow import AgentRunner, MultiAgentEngine

# Initialize (assuming router is configured)
agent_runner = AgentRunner(router)
multi_engine = MultiAgentEngine(agent_runner)
```

### Basic Usage
```python
result = multi_engine.process_with_multi_agents(
    user_input="Your user query here",
    user_id="user_123",
    conversation_id="conv_123"
)

print(result["final_output"])  # Get the result
```

### Check Result Status
```python
if result["status"] == "success":
    print(result["final_output"])
elif result["status"] == "needs_clarification":
    # Ask user the questions
    for q in result["clarification_questions"]:
        print(q)
elif result["status"] == "error":
    print(f"Error: {result['error']}")
```

---

## 📊 Key Components

### 1. **Three Agents** (Run automatically)
| Agent | Phase | Responsibility |
|-------|-------|-----------------|
| Intake Validator | 1 | Validate input, create plan |
| Research & Pricing | 2 | Research, gather pricing |
| Writer | 3 | Create output, cleanup |

### 2. **Communication Hub** (target.js)
- Agents read/write JSON
- Shared state between phases
- Auto-deleted after completion

### 3. **Trace System** (Complete logging)
- Records every action
- 45+ event types
- Performance metrics

---

## 🎯 Common Tasks

### Use Custom Prompts
```python
result = multi_engine.process_with_multi_agents(
    user_input="...",
    user_id="user_123",
    custom_prompts={
        "intake_validation": "Be strict about validation",
        "research_pricing": "Focus on budget options",
        "writing": "Use executive summary format"
    }
)
```

### Access Trace Information
```python
trace = result["trace"]
print(f"Total events: {trace['total_events']}")
print(f"Total time: {trace['total_duration_ms']}ms")
print(f"Events by agent: {trace['events_by_agent']}")

# Each event has:
# - timestamp
# - agent name
# - event type
# - data
# - metadata (duration, etc.)
```

### Modify Configuration
```python
from agent_file.utils.multi_agent_config import update_config, get_config_for_phase

# Update a setting
update_config("research_pricing", "max_api_calls", 20)

# Get phase config
config = get_config_for_phase("writing")
print(config["output_options"]["tone"])
```

### Handle Errors
```python
result = multi_engine.process_with_multi_agents(...)

if result["status"] == "error":
    error = result["error"]
    phase = result.get("phase")
    trace = result.get("trace")
    
    # Log/handle error
    log_error(phase, error, trace)
    
    # Optionally retry with better input
    retry_result = multi_engine.process_with_multi_agents(
        user_input="Better input",
        user_id=user_id,
        conversation_id=conversation_id  # Preserve context
    )
```

---

## 🔧 Advanced Tasks

### Access Phase-Specific Results
```python
result = multi_engine.process_with_multi_agents(...)

# Phase 1: Validation
validation = result["phases"]["intake_validation"]["validation"]
plan = result["phases"]["intake_validation"]["plan"]

# Phase 2: Research
research = result["phases"]["research_pricing"]["research"]
pricing = research.get("pricing_summary", {})
issues = research.get("issues_identified", [])

# Phase 3: Writing
output_meta = result["phases"]["writing"]["output_metadata"]
cleanup = result["phases"]["writing"]["cleanup"]
```

### Control Phases Separately
```python
# Phase 1
intake = agent_runner.intake_validator_agent(
    user_input="...",
    user_id="user_123",
    conversation_id="conv_123",
    request_id="req_123"
)

# Phase 2
research = agent_runner.research_pricing_agent(
    initial_plan=intake["result"]["validation"]["initial_plan"],
    workflow_context={
        "comm_manager": intake["comm_manager"],
        "trace_recorder": intake["trace_recorder"],
        "user_id": "user_123"
    }
)

# Phase 3
writing = agent_runner.writer_agent(
    research_data=research["result"]["research"],
    workflow_context={
        "comm_manager": research["comm_manager"],
        "trace_recorder": research["trace_recorder"],
        "user_id": "user_123"
    }
)
```

### Custom Prompt Variants
```python
from agent_file.utils.multi_agent_config import get_custom_prompt_for_phase, CUSTOM_PHASE_PROMPTS

# Use built-in variants
budget_variant = CUSTOM_PHASE_PROMPTS["research_pricing"]["custom_options"]["budget_focused"]

result = multi_engine.process_with_multi_agents(
    user_input="...",
    user_id="user_123",
    custom_prompts={
        "research_pricing": budget_variant
    }
)

# Or create your own
my_custom = "Your custom prompt here"
```

---

## 📈 Monitoring & Analytics

### Get Workflow Summary
```python
summary = result["workflow_summary"]
print(f"Workflow ID: {summary['workflow_id']}")
print(f"Current phase: {summary['current_phase']}")
print(f"Phase statuses: {summary['phase_statuses']}")
print(f"Total events: {summary['total_events']}")
```

### Analyze Performance
```python
trace = result["trace"]
for phase_name, phase_data in result["phases"].items():
    duration = phase_data.get("duration_ms", 0)
    print(f"{phase_name}: {duration}ms")

print(f"Total: {trace['total_duration_ms']}ms")
```

### Save Results
```python
import json

# Save complete workflow result
with open(f"workflow_{result['workflow_summary']['workflow_id']}.json", "w") as f:
    # Make datetime objects JSON serializable
    def serialize(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    json.dump(result, f, indent=2, default=serialize)

# Export just the final output
with open("final_output.md", "w") as f:
    f.write(result["final_output"])

# Save trace for analysis
with open("trace_log.json", "w") as f:
    json.dump(result["trace"], f, indent=2)
```

---

## 🐛 Troubleshooting

### "target.js not found"
```python
# Solution: Create it manually or check permissions
from pathlib import Path
target_file = Path("agent_file/target.js")
if not target_file.exists():
    target_file.touch()
```

### "Phase didn't complete"
```python
# Check trace for errors
if result["status"] == "error":
    events = result["trace"]["events"]
    errors = [e for e in events if e["event_type"] == "error"]
    for error_event in errors:
        print(error_event["data"])
```

### "LLM not responding"
```python
# Verify LLM is initialized
try:
    response = agent_runner.summary_llm.invoke([...])
except Exception as e:
    print(f"LLM Error: {e}")
    # Check connection, API key, rate limits
```

### "Memory/performance issues"
```python
from agent_file.utils.multi_agent_config import update_config

# Reduce API calls
update_config("research_pricing", "max_api_calls", 5)

# Disable detailed tracing
update_config("multi_agent_workflow", "tracing", {"enabled": False})

# Reduce timeout
update_config("multi_agent_workflow", "max_total_duration_seconds", 120)
```

---

## 📋 Configuration Quick Reference

### Phases Available
- `intake_validation` - Validate input
- `research_pricing` - Research & pricing
- `writing` - Final output

### Common Configs
```python
from agent_file.utils.multi_agent_config import update_config

# Increase research depth
update_config("research_pricing", "max_api_calls", 20)

# Change output format
update_config("writing", "output_format", "html")

# Adjust timeout
update_config("multi_agent_workflow", "max_total_duration_seconds", 300)

# Enable/disable tracing
update_config("multi_agent_workflow", "tracing", {"enabled": True})
```

### Output Formats
- `markdown` (default) - Formatted text
- `html` - HTML document
- `plain_text` - Plain text
- `json` - Structured JSON

### Tones
- `formal` - Very professional
- `professional_friendly` - Professional but approachable
- `casual` - Conversational
- `technical` - Uses technical terms

---

## 🔗 Integration with Existing Code

### With FastAPI
```python
from fastapi import FastAPI

app = FastAPI()
multi_engine = MultiAgentEngine(agent_runner)

@app.post("/query")
async def process_query(user_input: str, user_id: str):
    result = multi_engine.process_with_multi_agents(
        user_input=user_input,
        user_id=user_id
    )
    
    if result["status"] == "success":
        return {"output": result["final_output"]}
    elif result["status"] == "needs_clarification":
        return {"questions": result["clarification_questions"]}
    else:
        return {"error": result["error"]}, 400
```

### With Existing TravelEngine
```python
# Old single-agent
travel_engine = TravelEngine(agent_runner)

# New multi-agent
multi_engine = MultiAgentEngine(agent_runner)

# Can use both:
# - TravelEngine for simple queries
# - MultiAgentEngine for complex queries
```

---

## 📚 File Structure

```
agent_file/
├── agent/
│   ├── agentic_workflow.py       ← Main (modified)
│   └── multi_agents.py           ← New: 3 agents
├── utils/
│   ├── communication_manager.py  ← New: Inter-agent comm
│   ├── multi_agent_config.py     ← New: Configuration
│   └── ...
├── prompt_library/
│   ├── multi_agent_prompts.py    ← New: 3-phase prompts
│   └── ...
├── target.js                      ← New: Comm hub (auto-created)
├── __init__.py
├── ...

MULTI_AGENT_WORKFLOW_GUIDE.md     ← Full documentation
MULTI_AGENT_EXAMPLES.py            ← Code examples
MULTI_AGENT_QUICK_REF.md           ← This file
```

---

## 💡 Best Practices

✅ **DO:**
- Provide detailed user input
- Use custom prompts for specific behavior
- Monitor trace logs regularly
- Handle errors gracefully
- Test with examples first

❌ **DON'T:**
- Leave user_id empty
- Create target.js manually
- Modify target.js during workflow
- Ignore error status
- Use extremely long timeouts

---

## 🆘 Need Help?

1. Check `MULTI_AGENT_WORKFLOW_GUIDE.md` for detailed docs
2. Review examples in `MULTI_AGENT_EXAMPLES.py`
3. Check trace logs in result["trace"]
4. Verify configuration with `validate_config()`
5. Look at error details in result["error"]

---

## 📞 Support

For issues or questions:
1. Check the trace logs first
2. Review the full documentation
3. Look at similar examples
4. Check configuration settings
5. Verify LLM connectivity

Happy coding! 🚀
