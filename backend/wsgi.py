"""ABOUTME: WSGI entry point for production deployment
ABOUTME: Creates Flask application instance for WSGI servers like Gunicorn"""

from opendlp.entrypoints.flask_app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
