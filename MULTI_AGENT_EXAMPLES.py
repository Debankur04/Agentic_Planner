"""
Multi-Agent Workflow - Example Usage & Testing
Demonstrates how to use the three-phase agent system
"""

import asyncio
import json
from datetime import datetime

# ============ EXAMPLE 1: BASIC USAGE ============

def example_basic_usage():
    """
    Basic example: Process a user query through all 3 agents
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: BASIC MULTI-AGENT WORKFLOW")
    print("="*70 + "\n")
    
    from agent_file.agent.agentic_workflow import AgentRunner, MultiAgentEngine
    from agent_file.utils.model_loader import load_travel_planning_llm
    
    # Initialize router (assuming your router is set up)
    # For this example, we'll use mock data
    
    try:
        # Create agent runner
        # agent_runner = AgentRunner(router)
        # multi_engine = MultiAgentEngine(agent_runner)
        
        user_input = """
        I want to plan a romantic weekend trip to Paris for 2 people.
        Budget: $4000 total
        Dates: April 15-18, 2024
        Preferences: 5-star hotels, fine dining, cultural activities
        """
        
        # Process through all 3 phases
        # result = multi_engine.process_with_multi_agents(
        #     user_input=user_input,
        #     user_id="user_paris_001",
        #     conversation_id="conv_paris_2024"
        # )
        
        # Print result
        # print("\n✨ FINAL OUTPUT:")
        # print(result["final_output"])
        # 
        # print("\n📊 WORKFLOW METRICS:")
        # print(f"Total Duration: {result['trace']['total_duration_ms']}ms")
        # print(f"Total Events: {result['trace']['total_events']}")
        # print(f"Events by Agent:")
        # for agent, count in result['trace']['events_by_agent'].items():
        #     print(f"  - {agent}: {count} events")
        
        print("✅ Example ready (requires configured router)")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ============ EXAMPLE 2: WITH CUSTOM PROMPTS ============

def example_with_custom_prompts():
    """
    Example: Using custom prompts for each phase
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: WITH CUSTOM PROMPTS FOR EACH PHASE")
    print("="*70 + "\n")
    
    from agent_file.agent.agentic_workflow import AgentRunner, MultiAgentEngine
    
    try:
        # multi_engine = MultiAgentEngine(agent_runner)
        
        # Define custom prompts for specific behavior
        custom_prompts = {
            "intake_validation": """
            Be very strict about validation. 
            User must provide:
            - Destination
            - Travel dates
            - Budget
            - Number of travelers
            Ask clarification questions for any missing information.
            """,
            
            "research_pricing": """
            Find exactly 3 options: Budget, Mid-range, and Luxury.
            For each option provide:
            - Accommodation
            - Transportation
            - Activities
            - Estimated total cost
            Prioritize reliability and ratings.
            """,
            
            "writing": """
            Format as an executive summary.
            Use tables for price comparisons.
            Include a recommendation section.
            Keep it concise - max 500 words.
            Use professional but friendly tone.
            """
        }
        
        user_input = "Trip to Tokyo for 1 week, budget $3000, mid April"
        
        # result = multi_engine.process_with_multi_agents(
        #     user_input=user_input,
        #     user_id="user_tokyo_001",
        #     custom_prompts=custom_prompts
        # )
        
        print("✅ Example ready (requires configured router)")
        print("\nCustom prompts applied for:")
        for phase in custom_prompts.keys():
            print(f"  ✓ {phase}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ============ EXAMPLE 3: ERROR HANDLING & CLARIFICATION ============

def example_error_handling():
    """
    Example: Handling errors and clarification requests
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: ERROR HANDLING & CLARIFICATION")
    print("="*70 + "\n")
    
    from agent_file.agent.agentic_workflow import AgentRunner, MultiAgentEngine
    
    try:
        # multi_engine = MultiAgentEngine(agent_runner)
        
        # First attempt with incomplete info
        user_input = "I want to go on a trip"  # Too vague
        
        # result = multi_engine.process_with_multi_agents(
        #     user_input=user_input,
        #     user_id="user_test_001"
        # )
        
        # Handle different outcomes
        # if result["status"] == "needs_clarification":
        #     print("❓ CLARIFICATIONS NEEDED:")
        #     for i, question in enumerate(result["clarification_questions"], 1):
        #         print(f"  {i}. {question}")
        #     
        #     # Get answers from user
        #     print("\n✍️ ANSWERING CLARIFICATIONS:")
        #     clarified_input = """
        #     I want to go to Barcelona, Spain.
        #     Dates: May 1-7, 2024
        #     Budget: $2500 for 2 people
        #     Interests: Architecture, food, nightlife
        #     """
        #     
        #     # Retry with clarifications
        #     result = multi_engine.process_with_multi_agents(
        #         user_input=clarified_input,
        #         user_id="user_test_001",
        #         conversation_id="conv_test_001"
        #     )
        #     
        #     print("\n✅ RETRY SUCCESSFUL:")
        #     print(result["final_output"][:500] + "...")
        
        # elif result["status"] == "error":
        #     print(f"❌ ERROR: {result['error']}")
        #     print(f"Phase: {result['phase']}")
        #     print(f"Trace Events: {len(result['trace']['events'])}")
        
        print("✅ Example ready (requires configured router)")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ============ EXAMPLE 4: ACCESSING TRACE DATA ============

def example_trace_data():
    """
    Example: Accessing and analyzing trace data
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: TRACE DATA ANALYSIS")
    print("="*70 + "\n")
    
    from agent_file.agent.agentic_workflow import AgentRunner, MultiAgentEngine
    
    try:
        # multi_engine = MultiAgentEngine(agent_runner)
        
        # result = multi_engine.process_with_multi_agents(
        #     user_input="Trip to Iceland for 1 week, budget $5000",
        #     user_id="user_iceland_001"
        # )
        
        # Access trace information
        # trace = result["trace"]
        
        # print("📊 WORKFLOW TRACE SUMMARY:")
        # print(f"  Total Events: {trace['total_events']}")
        # print(f"  Total Duration: {trace['total_duration_ms']/1000:.2f}s")
        # print(f"\n  Events by Agent:")
        # for agent, count in trace['events_by_agent'].items():
        #     print(f"    - {agent}: {count}")
        # 
        # print(f"\n  Events by Type:")
        # for event_type, count in trace['events_by_type'].items():
        #     print(f"    - {event_type}: {count}")
        
        # print(f"\n📋 SAMPLE EVENTS (first 5):")
        # for i, event in enumerate(trace['events'][:5], 1):
        #     print(f"  {i}. [{event['event_type']}] {event['agent']}")
        #     print(f"     Time: {event['elapsed_ms']:.0f}ms")
        #     if event.get('data'):
        #         print(f"     Data: {str(event['data'])[:100]}...")
        
        # Access workflow summary
        # summary = result["workflow_summary"]
        # print(f"\n🎯 WORKFLOW SUMMARY:")
        # print(f"  Current Phase: {summary['current_phase']}")
        # print(f"  Phase Statuses:")
        # for phase, status in summary['phase_statuses'].items():
        #     print(f"    - {phase}: {status}")
        
        print("✅ Example ready (requires configured router)")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ============ EXAMPLE 5: CONFIGURATION CUSTOMIZATION ============

def example_configuration():
    """
    Example: Customizing workflow configuration
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: WORKFLOW CONFIGURATION")
    print("="*70 + "\n")
    
    from agent_file.utils.multi_agent_config import (
        MULTI_AGENT_WORKFLOW_CONFIG,
        get_config_for_phase,
        update_config,
        validate_config
    )
    
    try:
        # View current configuration
        print("📋 CURRENT CONFIGURATION:")
        print(f"  Workflow Enabled: {MULTI_AGENT_WORKFLOW_CONFIG['enabled']}")
        print(f"  Max Total Duration: {MULTI_AGENT_WORKFLOW_CONFIG['max_total_duration_seconds']}s")
        print(f"  Tracing Enabled: {MULTI_AGENT_WORKFLOW_CONFIG['tracing']['enabled']}")
        
        # Get specific phase config
        research_config = get_config_for_phase("research_pricing")
        print(f"\n🔬 RESEARCH & PRICING CONFIG:")
        print(f"  Max API Calls: {research_config['research_strategy']['max_api_calls']}")
        print(f"  Use Cache: {research_config['research_strategy']['use_cache']}")
        print(f"  Cache TTL: {research_config['research_strategy']['cache_ttl_seconds']}s")
        
        # Modify configuration
        print(f"\n✏️ MODIFYING CONFIGURATION:")
        update_config("research_pricing", "max_api_calls", 20)
        print(f"  Updated max_api_calls to 20")
        
        update_config("writing", "output_format", "json")
        print(f"  Updated output_format to json")
        
        # Validate
        if validate_config():
            print(f"\n✅ Configuration is valid")
        
        # Example: Budget-conscious workflow
        print(f"\n💰 BUDGET-CONSCIOUS WORKFLOW:")
        update_config("research_pricing", "max_api_calls", 5)
        print(f"  Reduced API calls to 5")
        update_config("writing", "output_options", {"tone": "cost_focused"})
        print(f"  Set tone to cost_focused")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ============ EXAMPLE 6: ADVANCED - PHASE-BY-PHASE CONTROL ============

def example_phase_control():
    """
    Example: Control each phase separately for advanced workflows
    """
    print("\n" + "="*70)
    print("EXAMPLE 6: PHASE-BY-PHASE CONTROL (ADVANCED)")
    print("="*70 + "\n")
    
    from agent_file.agent.agentic_workflow import AgentRunner
    from agent_file.utils.communication_manager import CommunicationManager, TraceRecorder
    from agent_file.agent.multi_agents import IntakeValidatorAgent
    
    try:
        # agent_runner = AgentRunner(router)
        
        # Initialize communication
        # comm_manager = CommunicationManager()
        # trace_recorder = TraceRecorder(comm_manager)
        
        # Phase 1: Intake Validation
        print("📋 PHASE 1: INTAKE VALIDATION")
        # result1 = agent_runner.intake_validator_agent(
        #     user_input="Trip to Bali for 3 weeks, budget $4000",
        #     user_id="user_bali_001",
        #     conversation_id="conv_bali",
        #     request_id="req_001"
        # )
        # print(f"  Status: {result1['result']['status']}")
        # print(f"  Duration: {result1['result']['duration_ms']:.0f}ms")
        
        # Phase 2: Research & Pricing (use output from Phase 1)
        print("\n🔍 PHASE 2: RESEARCH & PRICING")
        # initial_plan = result1['result']['validation'].get('initial_plan', {})
        # result2 = agent_runner.research_pricing_agent(
        #     initial_plan=initial_plan,
        #     workflow_context={
        #         "comm_manager": result1['comm_manager'],
        #         "trace_recorder": result1['trace_recorder'],
        #         "user_id": "user_bali_001"
        #     }
        # )
        # print(f"  Status: {result2['result']['status']}")
        # print(f"  API Calls: {result2['result']['api_calls_made']}")
        # print(f"  Duration: {result2['result']['duration_ms']:.0f}ms")
        
        # Phase 3: Writing (use output from Phase 2)
        print("\n📝 PHASE 3: WRITING & CLEANUP")
        # research_data = result2['result']['research']
        # result3 = agent_runner.writer_agent(
        #     research_data=research_data,
        #     workflow_context={
        #         "comm_manager": result2['comm_manager'],
        #         "trace_recorder": result2['trace_recorder'],
        #         "user_id": "user_bali_001"
        #     }
        # )
        # print(f"  Status: {result3['result']['status']}")
        # print(f"  Output Length: {len(result3['result']['final_output'])} chars")
        # print(f"  Cleanup: {result3['result']['cleanup']['status']}")
        # print(f"  Duration: {result3['result']['duration_ms']:.0f}ms")
        
        print("\n✅ Example ready (requires configured router)")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ============ INTEGRATION TEST ============

def run_integration_test():
    """
    Run all examples
    """
    print("\n" + "="*70)
    print("MULTI-AGENT WORKFLOW EXAMPLES & INTEGRATION TEST")
    print("="*70)
    
    examples = [
        example_basic_usage,
        example_with_custom_prompts,
        example_error_handling,
        example_trace_data,
        example_configuration,
        example_phase_control
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"❌ Error running {example.__name__}: {e}")
    
    print("\n" + "="*70)
    print("EXAMPLES COMPLETE")
    print("="*70)


if __name__ == "__main__":
    run_integration_test()
