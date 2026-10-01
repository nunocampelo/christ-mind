import os

# The entity_relation channel (describe_entity) is registered only when this flag is set
# (server.py reads it at import time, so it must be set before any test imports the
# server). The suite exercises the tool, so enable it for the whole test session.
os.environ.setdefault("ENTITY_RELATION_ENABLED", "1")
