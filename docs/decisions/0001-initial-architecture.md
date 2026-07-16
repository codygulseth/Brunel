# 0001: Initial architecture

**Status:** Accepted

Brunel's initial responsibility-registry prototype uses one FastAPI application with Jinja2 templates, SQLAlchemy 2, Pydantic validation, and a local SQLite database. Keep queries in a small service layer and use dependency injection for database sessions.

This architecture is easy to run, test, and understand. It avoids a frontend build system, cloud services, authentication, and AI dependencies while leaving clear seams for later editing workflows and document-grounded features.
