# Deployment Guide

## Subpath Deployment

OpenDLP can be deployed under a subpath (e.g., `example.com/opendlp/`) rather than at the domain root.

### Configuration

Set the `APPLICATION_ROOT` configuration variable:

```python
# In your .env file
APPLICATION_ROOT=/opendlp

# Or in environment variables
export APPLICATION_ROOT=/opendlp
```

### Reverse Proxy Configuration

#### Nginx

```nginx
location /opendlp/ {
    proxy_pass http://localhost:5000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Important: Strip the subpath prefix when forwarding
    proxy_set_header X-Script-Name /opendlp;
}
```

#### Apache

```apache
ProxyPreserveHost On
ProxyPass /opendlp/ http://localhost:5000/
ProxyPassReverse /opendlp/ http://localhost:5000/

# Set script name for Flask
ProxyPassReverse /opendlp/ http://localhost:5000/
Header always set X-Script-Name "/opendlp"
```

#### Traefik

```yaml
http:
  routers:
    opendlp:
      rule: "Host(`example.com`) && PathPrefix(`/opendlp`)"
      middlewares:
        - opendlp-stripprefix
      service: opendlp

  middlewares:
    opendlp-stripprefix:
      stripPrefix:
        prefixes:
          - "/opendlp"

  services:
    opendlp:
      loadBalancer:
        servers:
          - url: "http://localhost:5000"
```

### WSGI Configuration

For production WSGI deployment, wrap the Flask app:

```python
# wsgi.py
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from opendlp.entrypoints.flask_app import create_app

application = DispatcherMiddleware(
    None,  # Default app (404 for root)
    {'/opendlp': create_app()}
)
```

Or use `APPLICATION_ROOT` in the Flask app configuration.

### Docker Deployment

When using Docker with subpath deployment:

```dockerfile
# Set environment variable in Dockerfile or docker-compose.yml
ENV APPLICATION_ROOT=/opendlp
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  opendlp:
    build: .
    environment:
      - APPLICATION_ROOT=/opendlp
    labels:
      - "traefik.http.routers.opendlp.rule=Host(`example.com`) && PathPrefix(`/opendlp`)"
      - "traefik.http.middlewares.opendlp-strip.stripprefix.prefixes=/opendlp"
      - "traefik.http.routers.opendlp.middlewares=opendlp-strip"
```

## Required Code Changes

The following changes are needed to support subpath deployment:

### 1. Flask Configuration (config.py)

```python
# Add to FlaskConfig class
def __init__(self) -> None:
    # ... existing config ...
    self.APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/")
```

### 2. URL Generation

All templates and redirects already use `url_for()` which will automatically respect `APPLICATION_ROOT` - no changes needed.

### 3. Static Files

Static file URLs are handled by Flask's `url_for('static', filename='...')` which respects `APPLICATION_ROOT` - no changes needed.

### 4. CSRF and Session Cookies

Flask-WTF and Flask-Session will automatically use the correct cookie path based on `APPLICATION_ROOT` - no changes needed.

## Testing Subpath Deployment

Test subpath deployment locally:

```bash
# Set APPLICATION_ROOT
export APPLICATION_ROOT=/opendlp

# Run Flask development server
uv run flask run

# Test URLs
curl http://localhost:5000/opendlp/
curl http://localhost:5000/opendlp/auth/login
```

## Security Considerations

- Ensure reverse proxy strips the subpath prefix correctly
- Verify that redirects and form actions use absolute URLs
- Check that static files are served with correct paths
- Confirm session cookies have the appropriate path restriction

## Further Reading

- [Flask Documentation: Application Dispatching](https://flask.palletsprojects.com/en/3.0.x/patterns/appdispatch/)
- [Werkzeug Middleware](https://werkzeug.palletsprojects.com/en/3.0.x/middleware/)
- [Deploying to a subpath](https://flask.palletsprojects.com/en/3.0.x/config/#APPLICATION_ROOT)
