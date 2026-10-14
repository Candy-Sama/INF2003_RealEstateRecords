"""Connection placeholders for the planned MySQL and MongoDB databases."""


def get_mysql_connection():
    """Create and return a MySQL connection once credentials and driver are configured."""
    raise NotImplementedError(
        "Implement the MySQL connection here using your project configuration."
    )


def get_mongodb_connection():
    """Create and return a MongoDB client or database once configured."""
    raise NotImplementedError(
        "Implement the MongoDB connection here using your project configuration."
    )
