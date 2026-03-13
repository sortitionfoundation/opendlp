# Code Quality Rules

This document collects code quality rules and patterns to follow, gathered from code review feedback and linting issues.

## Exception Handling

### Never use bare `pass` in exception handlers

**Rule:** Exception handlers should never use a bare `pass` statement. Always log the exception, even if the behavior is to silently continue.

**Why:** Bare `pass` statements make debugging difficult because there's no trace of what happened. Even when silently ignoring an exception is the correct behavior, logging at `debug` level provides observability.

**Bad:**
```python
try:
    value = uuid.UUID(some_param)
except (ValueError, TypeError):
    pass  # No trace of what happened
```

**Good:**
```python
try:
    value = uuid.UUID(some_param)
except (ValueError, TypeError):
    current_app.logger.debug("Invalid UUID parameter: %r", some_param)
```

**Log levels:**
- Use `debug` for expected invalid input that's gracefully handled
- Use `warning` for unexpected but recoverable situations
- Use `error` for failures that affect functionality

## Cyclomatic Complexity

### Keep functions under complexity threshold (C901)

**Rule:** Functions should have a cyclomatic complexity of 10 or less (configured in ruff).

**Why:** High complexity makes code harder to understand, test, and maintain.

**Solutions:**
1. Extract helper functions for distinct logical blocks
2. Use early returns to reduce nesting
3. Replace complex conditionals with lookup tables or strategy patterns

**Example refactoring:**
```python
# Before: Complex function with nested conditionals
def process_data(data, option_a, option_b):
    if option_a:
        if data.type == "x":
            # 20 lines of logic
        else:
            # 20 lines of logic
    if option_b:
        # more nested logic
    # ... complexity grows

# After: Extract helper functions
def _process_type_x(data):
    # focused logic

def _process_other_types(data):
    # focused logic

def process_data(data, option_a, option_b):
    if option_a:
        if data.type == "x":
            return _process_type_x(data)
        return _process_other_types(data)
    # cleaner main function
```

## Import Organization

### Keep imports at module level (PLC0415)

**Rule:** All `import` statements should be at the top of the file, not inside functions.

**Why:**
- Imports inside functions hide dependencies
- Makes it harder to see what a module depends on
- Can cause unexpected performance issues (import on every call)

**Exceptions:** Circular import resolution may require local imports, but these should be documented.

## Code Formatting

### Run pre-commit hooks before committing

**Rule:** Always run `just check` before committing to catch formatting issues.

**Tools configured:**
- `ruff check` - Linting (includes complexity checks)
- `ruff format` - Code formatting
- `DjHTML` - HTML template formatting
- `DjCSS` - CSS formatting
- `DjJS` - JavaScript formatting
- `mypy` - Type checking
