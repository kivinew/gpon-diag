# Task Card: External Control Loop System

## Objective
Develop system for external control loop to verify AI agent task completion in the gpon-diag project.

## Requirements
- Check if task achieved desired result
- If not achieved, task remains incomplete and returns to agent for revision
- Integration with existing orchestrator components

## Design

### TaskVerificationResult
```python
@dataclass
class TaskVerificationResult:
    success: bool
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]
```

### ExternalControlLoop
```python
class ExternalControlLoop:
    def verify_task_completion(self, task_card: TaskCard) -> TaskVerificationResult
    def request_revision(self, task_card: TaskCard, errors: List[str]) -> None
    def approve_completion(self, task_card: TaskCard) -> None
```

### Integration Points
- Uses validator.py for code validation
- Uses agent_registry.py for agent status tracking
- Creates .task_cards/ directory for task storage

## Status
pending