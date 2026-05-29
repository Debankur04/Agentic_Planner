"""
Multi-Agent Workflow Configuration
Defines customizable settings for each phase
"""

# ============ PHASE 1: INTAKE VALIDATION ============

INTAKE_VALIDATION_CONFIG = {
    "enabled": True,
    "max_retries": 1,
    "timeout_seconds": 30,
    "required_fields": [
        "user_input",
        "user_id"
    ],
    "validation_rules": {
        "min_input_length": 10,
        "max_input_length": 5000,
        "check_for_ambiguities": True,
        "extract_entities": True
    },
    "confidence_threshold": 60,  # Minimum confidence to proceed
    "ask_for_clarification_below": 70,  # Ask clarification if below this
    "trace_level": "detailed"  # minimal, normal, detailed
}

# ============ PHASE 2: RESEARCH & PRICING ============

RESEARCH_PRICING_CONFIG = {
    "enabled": True,
    "max_retries": 2,
    "timeout_seconds": 120,
    "research_strategy": {
        "use_cache": True,
        "cache_ttl_seconds": 300,
        "max_api_calls": 10,
        "parallel_search": False,
        "cross_reference_sources": True
    },
    "pricing_options": {
        "min_options_required": 1,
        "max_options_to_show": 5,
        "include_alternatives": True
    },
    "issue_detection": {
        "severity_levels": ["low", "medium", "high"],
        "flag_unusual_results": True,
        "data_quality_check": True
    },
    "trace_level": "detailed"
}

# ============ PHASE 3: WRITING ============

WRITING_CONFIG = {
    "enabled": True,
    "max_retries": 1,
    "timeout_seconds": 60,
    "output_format": "markdown",  # markdown, html, plain_text, json
    "output_options": {
        "include_pricing": True,
        "include_disclaimers": True,
        "include_recommendations": True,
        "include_next_steps": True,
        "tone": "professional_friendly",  # formal, professional_friendly, casual, technical
        "detail_level": "moderate"  # brief, moderate, detailed
    },
    "formatting": {
        "use_sections": True,
        "use_tables": True,
        "use_lists": True,
        "max_lines_per_section": 50,
        "include_summary": True
    },
    "cleanup": {
        "delete_target_file": True,
        "delete_backups": True,
        "log_cleanup_details": True
    },
    "trace_level": "detailed"
}

# ============ GLOBAL WORKFLOW CONFIG ============

MULTI_AGENT_WORKFLOW_CONFIG = {
    "enabled": True,
    "workflow_name": "Multi-Agent Travel Planning",
    "max_total_duration_seconds": 300,
    "inter_agent_communication": {
        "method": "json_file",  # json_file, redis, database
        "file_path": "agent_file/target.js",
        "auto_cleanup": True,
        "backup_on_write": True
    },
    "tracing": {
        "enabled": True,
        "log_to_file": True,
        "log_path": "logs/workflow_trace.log",
        "log_level": "INFO",
        "save_trace_summary": True
    },
    "error_handling": {
        "stop_on_phase_error": False,
        "max_retries_per_phase": 1,
        "fallback_strategy": "return_error",  # return_error, partial_result, retry
        "notify_on_error": False
    },
    "phases": {
        "intake_validation": INTAKE_VALIDATION_CONFIG,
        "research_pricing": RESEARCH_PRICING_CONFIG,
        "writing": WRITING_CONFIG
    }
}

# ============ CUSTOM PHASE PROMPTS ============

CUSTOM_PHASE_PROMPTS = {
    "intake_validation": {
        "default": None,  # Use built-in
        "custom_options": {
            "strict": "Be very strict about validation. Return 'invalid' if anything is unclear.",
            "lenient": "Be lenient and helpful. Try to interpret ambiguities positively.",
            "technical": "Use technical language and focus on precise specifications."
        }
    },
    "research_pricing": {
        "default": None,
        "custom_options": {
            "budget_focused": "Prioritize budget and cost options",
            "quality_focused": "Prioritize quality and premium options",
            "balanced": "Balance between quality and price"
        }
    },
    "writing": {
        "default": None,
        "custom_options": {
            "concise": "Make the output very concise and scannable",
            "comprehensive": "Provide comprehensive details and explanations",
            "executive_summary": "Format as an executive summary"
        }
    }
}

# ============ HELPER FUNCTIONS ============

def get_config_for_phase(phase_name: str) -> dict:
    """Get configuration for a specific phase"""
    return MULTI_AGENT_WORKFLOW_CONFIG["phases"].get(phase_name, {})

def get_custom_prompt_for_phase(phase_name: str, prompt_type: str = "default") -> str:
    """Get custom prompt for a specific phase"""
    phase_prompts = CUSTOM_PHASE_PROMPTS.get(phase_name, {})
    return phase_prompts.get(prompt_type)

def update_config(phase_name: str, key: str, value: any) -> bool:
    """Update a configuration value"""
    try:
        if phase_name in MULTI_AGENT_WORKFLOW_CONFIG["phases"]:
            config = MULTI_AGENT_WORKFLOW_CONFIG["phases"][phase_name]
            config[key] = value
            return True
        return False
    except Exception as e:
        print(f"Error updating config: {e}")
        return False

def validate_config() -> bool:
    """Validate configuration is well-formed"""
    required_phases = ["intake_validation", "research_pricing", "writing"]
    for phase in required_phases:
        if phase not in MULTI_AGENT_WORKFLOW_CONFIG["phases"]:
            print(f"Missing phase configuration: {phase}")
            return False
    return True
