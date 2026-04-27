"""Gunicorn / dev entry point. `gunicorn -k eventlet -w 1 app:app`."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
