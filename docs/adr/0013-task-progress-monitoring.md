# ADR-008: Task Progress Monitoring for Background Tasks

## Status

Proposed

## Context

OpenDLP uses Celery for background tasks, particularly for long-running stratified selection processes. Users need real-time feedback on task progress to understand that the system is working and see how long operations will take. The current system only provides basic status tracking (running, complete, failed) without progress updates.

The frontend uses Flask/Jinja templates with HTMX and Alpine.js for interactivity, avoiding heavy JavaScript frameworks. The application already uses Redis for session storage, providing existing infrastructure for real-time communication.

## Decision

We will implement **Server-Sent Events (SSE)** with Redis pub/sub for task progress monitoring, integrated with HTMX and Alpine.js on the frontend.

### Architecture

1. **Celery tasks** publish progress updates to Redis using pub/sub channels
2. **Flask SSE endpoint** subscribes to Redis channels and streams progress to browsers
3. **Alpine.js components** handle real-time UI updates (progress bars, status messages)
4. **HTMX integration** loads final results when tasks complete

### Communication Flow

```txt
Celery Task → Redis Pub/Sub → Flask SSE Endpoint → Browser EventSource → Alpine.js
                                     ↓
                              When Complete → HTMX → Load Results
```

## Alternatives Considered

### WebSockets with Flask-SocketIO

- **Pros**: Bidirectional, robust connection handling
- **Cons**: More complex setup, requires persistent connections, additional dependency
- **Decision**: Rejected due to added complexity for unidirectional use case

### AJAX Polling + Database

- **Pros**: Simple implementation, universal browser support
- **Cons**: Not truly real-time, higher database load, inefficient
- **Decision**: Rejected due to poor user experience and resource usage

### AJAX Polling + Redis

- **Pros**: Fast polling, less database load than database polling
- **Cons**: Still polling overhead, not truly real-time
- **Decision**: Rejected in favor of push-based approach

## Implementation Details

### Frontend (Alpine.js + HTMX)

```html
<div x-data="sseProgress('{{ task_id }}')" class="govuk-width-container">
  <!-- GOV.UK progress bar and status display -->
  <div :style="`width: ${progress}%; background: #00703c;`"></div>
  <p x-text="currentMessage"></p>
</div>
```

### Backend (Flask SSE)

```python
@app.route('/task/<task_id>/progress')
def task_progress_stream(task_id):
    def event_stream():
        # Subscribe to Redis pub/sub
        # Yield SSE formatted progress updates
    return Response(event_stream(), mimetype='text/event-stream')
```

### Celery Integration

```python
def publish_progress(task_id, progress_data):
    redis_client.publish(f"task_progress:{task_id}", json.dumps(progress_data))
```

## Benefits

1. **Real-time Updates**: Users see immediate progress feedback
2. **Lightweight**: Native browser EventSource, no additional client libraries
3. **Scalable**: Uses existing Redis infrastructure
4. **Framework Integration**: Works seamlessly with HTMX and Alpine.js
5. **Graceful Degradation**: Can fallback to HTMX polling if SSE fails
6. **GOV.UK Compatible**: Integrates with existing design system

## Risks

1. **Browser Compatibility**: EventSource not supported in older browsers
2. **Connection Limits**: Browsers limit concurrent SSE connections per domain
3. **Network Issues**: Long-running connections may timeout or disconnect

## Mitigation Strategies

1. **Fallback Mechanism**: Detect SSE support and fallback to HTMX polling
2. **Connection Management**: Close SSE connections when tasks complete
3. **Reconnection Logic**: Implement automatic reconnection in Alpine.js components
4. **Timeout Handling**: Set appropriate timeouts and retry logic

## Success Metrics

- Users can see real-time progress during stratified selection
- Progress updates appear within 1 second of task state changes
- System handles concurrent task monitoring for multiple users
- Fallback mechanism works for unsupported browsers

## Implementation Priority

This will be implemented after Celery integration is complete and before public deployment, as user feedback during long-running selections is critical for user experience.
