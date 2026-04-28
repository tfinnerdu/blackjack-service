"""Gunicorn / dev entry point. `gunicorn -k gthread --threads 4 -w 1 wsgi:app`.

Named wsgi.py rather than app.py to avoid colliding with the `app/`
package — Python prefers packages over modules with the same name, so
`app:app` fails to find the WSGI callable.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True, use_reloader=False)
