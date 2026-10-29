"""Database connection factories configured through environment variables."""

import os


def get_mysql_connection():
    """Connect to the configured MySQL schema."""
    import mysql.connector

    database = os.getenv("MYSQL_DATABASE")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    if not database or not user or password is None:
        raise ValueError(
            "Set MYSQL_DATABASE, MYSQL_USER, and MYSQL_PASSWORD before connecting."
        )

    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=database,
        user=user,
        password=password,
    )


def get_mongodb_client():
    """Create a MongoDB client for the configured local or remote server."""
    from pymongo import MongoClient

    return MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))


def get_mongodb_database_name() -> str:
    """Return the MongoDB database that stores saved-search documents."""
    return os.getenv("MONGODB_DATABASE", "estate_records")
