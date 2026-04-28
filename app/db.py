"""SQLAlchemy instance, separated to avoid circular imports."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
