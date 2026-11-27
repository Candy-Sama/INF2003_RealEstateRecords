"""Repeat the documented saved-search benchmark on a loopback MongoDB server."""

import os
from contextlib import contextmanager
from datetime import date, timedelta
from statistics import median
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4

from bson import json_util

from app.app_modules.database.database import get_mongodb_client
from app.app_modules.saved_searches_store import (
    SAVED_SEARCH_INDEX, SAVED_SEARCH_INDEX_NAME, SAVED_SEARCH_SORT,
)

from .run_mysql_evidence import LOOPBACK, write_json


@contextmanager
def disposable_mongo():
    endpoint = urlparse(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    if (endpoint.scheme != "mongodb" or endpoint.hostname not in LOOPBACK or
            "," in endpoint.netloc.rsplit("@", 1)[-1]):
        raise ValueError("Use a loopback MongoDB server for evidence.")
    with get_mongodb_client() as client:
        # Refuse a topology that can route fixture operations to a non-loopback primary.
        hello = client.admin.command("hello")
        if hello.get("setName") or hello.get("msg") == "isdbgrid":
            raise ValueError("Use a standalone loopback MongoDB server for evidence.")
        name = "estate_evidence_" + uuid4().hex
        try:
            yield client[name]
        finally:
            client.drop_database(name)


def stages(node):
    if isinstance(node, dict):
        if "stage" in node:
            yield node["stage"]
        for value in node.values():
            yield from stages(value)
    elif isinstance(node, list):
        for value in node:
            yield from stages(value)


def measure(collection, owner, samples):
    command = {"explain": {"find": collection.name, "filter": owner, "sort": dict(SAVED_SEARCH_SORT)},
               "verbosity": "executionStats"}
    explain = []
    elapsed = []
    for _ in range(3):
        list(collection.find(owner).sort(SAVED_SEARCH_SORT))
    for _ in range(samples):
        result = collection.database.command(command)
        stats = result["executionStats"]
        plan = result["queryPlanner"]["winningPlan"]
        explain.append({
            "planStages": list(stages(plan)),
            "winningPlan": json_util.loads(json_util.dumps(plan)),
            "nReturned": stats["nReturned"],
            "totalKeysExamined": stats["totalKeysExamined"],
            "totalDocsExamined": stats["totalDocsExamined"],
            "executionTimeMillis": stats["executionTimeMillis"],
            "explicitSort": "SORT" in stages(plan),
        })
        started = perf_counter()
        documents = list(collection.find(owner).sort(SAVED_SEARCH_SORT))
        elapsed.append(round((perf_counter() - started) * 1000, 6))
    return documents, {"explain": explain, "client_fetch_ms": elapsed, "client_median_ms": median(elapsed)}


def main():
    owner = {"agent_id": 42}
    payload = [
        {"agent_id": agent, "name": f"Benchmark {number}",
         "filters": {"town": "TAMPINES", "flat_type": "4 ROOM"},
         "created_at": (date(2026, 1, 1) + timedelta(days=number)).isoformat()}
        for agent in range(1, 201) for number in range(100)
    ]
    rounds = []
    with disposable_mongo() as database:
        version = database.client.server_info()["version"]
        for _ in range(3):
            collection = database[f"tmp_saved_search_bench_{uuid4().hex}"]
            try:
                # PyMongo attaches IDs to inserted documents. Copy before each new trial.
                collection.insert_many([doc.copy() for doc in payload])
                before, baseline = measure(collection, owner, 15)
                collection.create_index(SAVED_SEARCH_INDEX, name=SAVED_SEARCH_INDEX_NAME)
                after, indexed = measure(collection, owner, 15)
                assert len(before) == 100 and before == after
                rounds.append({"before": baseline, "after": indexed, "same_ordered_documents": before == after})
            finally:
                collection.drop()
    write_json("mongodb-benchmark.json", {
        "mongodb": version, "documents_per_fixture": len(payload), "agents": 200,
        "owner_filter": owner, "sort": SAVED_SEARCH_SORT, "compound_index": SAVED_SEARCH_INDEX,
        "compound_index_name": SAVED_SEARCH_INDEX_NAME, "warmups_per_layout": 3,
        "explain_and_fetch_samples_per_layout_per_trial": 15, "trials": rounds,
    })


if __name__ == "__main__":
    main()
