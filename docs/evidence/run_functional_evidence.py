"""Exercise the Streamlit workspace and production stores against disposable databases."""

import os
from contextlib import closing
from datetime import date
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from app import repository
from app.app_modules import saved_searches_store as searches
from app.app_modules.analytics import analytics_sql, analytics_store as cards
from app.app_modules.analytics.analytics_defaults import DEFAULT_CARDS
from app.app_modules.database.database import get_mongodb_client, get_mysql_connection
from app.app_modules.security.security import hash_password

from .run_mongodb_evidence import disposable_mongo
from .run_mysql_evidence import ROOT, disposable_schema


PASSWORD = uuid4().hex
EMAIL_A = "agent-a@example.invalid"
EMAIL_B = "agent-b@example.invalid"
ADMIN_EMAIL = "fixture-admin@example.invalid"
SALE_DAY = date(2025, 3, 31)


def report(message):
    print(f"PASS | {message}", flush=True)


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def page(app, label):
    app.radio(key="workspace_section").set_value(label).run()
    assert not app.exception and not app.error


def login(app, email, password=PASSWORD):
    app.text_input[0].input(email)
    app.text_input[1].input(password)
    click(app, "Log in")


def register(app, name, email):
    inputs = {widget.label: widget for widget in app.tabs[1].text_input}
    inputs["Full name"].input(name)
    inputs["Email address"].input(email)
    inputs["Phone number"].input("00000000")
    inputs["Create password"].input(PASSWORD)
    inputs["Confirm password"].input(PASSWORD)
    click(app, "Create account")
    assert app.session_state["agent"]["email"] == email
    return app.session_state["agent"]["agent_id"]


def fresh_app():
    app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=20).run()
    assert not app.exception
    return app


def seed_relational_fixture():
    with closing(get_mysql_connection()) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO place VALUES (1, '1', 'TEST ROAD', '000001', 1.35, 103.80, 'TAMPINES')")
        cursor.execute("INSERT INTO flat VALUES (1, '4 ROOM', 'MODEL', '01 TO 03', 90.25, 1, 1982, 780)")
        connection.commit()
        repository.create_agent(connection, "Fixture administrator", ADMIN_EMAIL, "00000000", hash_password(PASSWORD))


def verify_registration(app):
    agent_a = register(app, "Evidence A", EMAIL_A)
    assert any(item.value == "Account created." for item in app.success)
    click(app, "Log out")
    for widget in app.tabs[1].text_input:
        if widget.label == "Full name":
            widget.input("Reserved account")
        elif widget.label == "Email address":
            widget.input(ADMIN_EMAIL)
        elif widget.label == "Phone number":
            widget.input("00000000")
        else:
            widget.input(PASSWORD)
    click(app, "Create account")
    assert any("must be provisioned" in item.value for item in app.error)
    login(app, EMAIL_A, "incorrect-password")
    assert any("incorrect" in item.value for item in app.error) and "agent" not in app.session_state
    login(app, EMAIL_A.upper())
    assert app.session_state["agent"]["agent_id"] == agent_a
    with closing(get_mysql_connection()) as connection:
        account = repository.find_agent_by_email(connection, EMAIL_A)
        assert account["password_hash"].startswith("scrypt$") and account["password_hash"] != PASSWORD
    report("Streamlit registration, reserved administrator registration rejection, incorrect password rejection, case-normalized login and salted scrypt storage")
    return agent_a


def verify_transactions(app, agent_a):
    page(app, "My transactions")
    app.number_input(key="create_transaction_flat_id").set_value(1)
    app.date_input(key="create_transaction_date").set_value(SALE_DAY)
    app.number_input(key="create_transaction_price").set_value(500000.19)
    click(app, "Create transaction")
    assert len(app.dataframe) == 1 and any(item.value == "Transaction created." for item in app.success)
    app.radio(key="transaction_action").set_value("Update").run()
    click(app, "Find my transaction")
    app.number_input(key="edit_transaction_price_1").set_value(525000.27)
    click(app, "Save transaction")
    with closing(get_mysql_connection()) as connection:
        assert repository.get_agent_transaction(connection, agent_a, 1)["resale_price"] == Decimal("525000.27")
    report("Streamlit resale create, owner list and update, verified from a separate MySQL connection")


def verify_saved_search_ui(app, db, agent_a):
    page(app, "Search & filter")
    app.selectbox(key="filter_town").select("TAMPINES")
    app.selectbox(key="filter_flat_type").select("4 ROOM")
    click(app, "Search records")
    assert len(app.session_state["last_search_results"]) == 1
    next(widget for widget in app.text_input if widget.label == "Name this search").input("Fixture search")
    click(app, "Save search")
    assert any(item.value == "Search saved." for item in app.success)
    saved, = searches.list_searches(db, agent_a)
    page(app, "Saved searches")
    search_id = saved["_id"]
    prefix = f"saved_search_edit_{search_id}"
    app.text_input(key=f"{prefix}_name").input("Fixture search edited")
    app.number_input(key=f"{prefix}_max_price").set_value(600000)
    click(app, "Save changes")
    edited, = searches.list_searches(db, agent_a)
    assert edited["name"] == "Fixture search edited" and edited["filters"]["max_price"] == 600000

    # Older AppTest versions can retain duplicate form widgets after an internal rerun.
    app.run()
    assert not app.exception and not app.error
    app.number_input(key=f"{prefix}_min_price").set_value(650000)
    click(app, "Save changes")
    assert any("Minimum price" in item.value for item in app.error)
    app.number_input(key=f"{prefix}_min_price").set_value(0)
    app.date_input(key=f"{prefix}_start_date").set_value(date(2025, 3, 30))
    app.date_input(key=f"{prefix}_end_date").set_value(date(2025, 3, 1))
    click(app, "Save changes")
    assert any("Start date" in item.value for item in app.error)
    assert searches.list_searches(db, agent_a) == [edited]
    report("Streamlit saved-search create, retrieval, edit and rejection of inverted prices and dates, with persisted values unchanged")

    with closing(get_mysql_connection()) as connection:
        assert repository.update_agent_transaction(connection, agent_a, 1, 1, SALE_DAY, Decimal("560000.35"))
    click(app, "Run saved search")
    assert app.radio(key="workspace_section").value == "Search & filter"
    assert app.session_state["last_search_filters"] == edited["filters"]
    rerun_rows = app.session_state["last_search_results"]
    assert [row["resale_price"] for row in rerun_rows] == [Decimal("560000.35")]
    click(app, "Search records")
    assert app.session_state["last_search_results"] == rerun_rows
    assert not {"results", "rows", "last_search_results"}.intersection(edited)
    report("Run saved search restored filters and returned the updated MySQL price, matching direct search")
    return search_id


def verify_isolation(app, db, agent_a, search_id):
    click(app, "Log out")
    assert "last_search_results" not in app.session_state
    agent_b = register(app, "Evidence B", EMAIL_B)
    assert not app.dataframe
    click(app, "Search records")
    assert [row["resale_price"] for row in app.session_state["last_search_results"]] == [Decimal("560000.35")]
    page(app, "Saved searches")
    assert any("no saved searches" in item.value for item in app.info)
    assert searches.update_search(db, agent_b, search_id, "Foreign edit", {}) is None
    assert not searches.delete_search(db, agent_b, search_id)
    assert searches.list_searches(db, agent_a)[0]["name"] == "Fixture search edited"

    page(app, "My transactions")
    assert not app.dataframe
    for action in ("Update", "Delete"):
        app.radio(key="transaction_action").set_value(action).run()
        click(app, "Find my transaction")
        assert any("no longer exists in your account" in item.value for item in app.warning)
        assert not any(button.label in {"Save transaction", "Delete transaction"} for button in app.button)
    with closing(get_mysql_connection()) as connection:
        assert repository.get_agent_transaction(connection, agent_b, 1) is None
        assert not repository.update_agent_transaction(connection, agent_b, 1, 1, SALE_DAY, Decimal("1"))
        assert not repository.delete_agent_transaction(connection, agent_b, 1)
        assert repository.get_agent_transaction(connection, agent_a, 1)["resale_price"] == Decimal("560000.35")
    page(app, "Flat records")
    assert any("read-only" in item.value for item in app.caption)
    assert any(button.label == "Find flat" for button in app.button)
    assert not any(button.label in {"Create flat", "Save changes"} for button in app.button)
    click(app, "Find flat")
    assert len(app.dataframe) == 2
    report("Same-session account switch, agent-scoped MySQL read/update/delete, shared market search, MongoDB saved-search ownership and read-only flat catalogue for regular agents")

    click(app, "Log out")
    login(app, EMAIL_A)
    page(app, "Saved searches")
    click(app, "Delete saved search")
    assert not searches.list_searches(db, agent_a) and any(item.value == "Saved search deleted." for item in app.success)
    page(app, "My transactions")
    app.radio(key="transaction_action").set_value("Delete").run()
    click(app, "Find my transaction")
    click(app, "Delete transaction")
    assert any(item.value == "Transaction deleted." for item in app.success)
    with closing(get_mysql_connection()) as connection:
        assert repository.get_agent_transaction(connection, agent_a, 1) is None
    report("Streamlit owner successfully deleted the saved search and resale transaction")
    return agent_b


def verify_dashboard(app, db, agent_a, agent_b):
    page(app, "Analytics")
    default_keys = {card["seed_key"] for card in DEFAULT_CARDS}
    assert {card["seed_key"] for card in cards.list_cards(db, agent_a)} == default_keys
    assert cards.seed_defaults(db, agent_a) == 0
    assert cards.seed_defaults(db, agent_b) == len(default_keys)
    page(app, "Search & filter")
    card = {"title": "Evidence custom card", "sql": "SELECT COUNT(*) AS sale_count FROM resale_transaction",
            "display_type": "table"}
    card_id = cards.create_card(db, agent_a, card)
    duplicate_id = cards.duplicate_card(db, agent_a, card_id)
    copied = next(item for item in cards.list_cards(db, agent_a) if item["id"] == duplicate_id)
    assert copied["title"] == "Copy of Evidence custom card" and copied["sql"] == card["sql"]
    cards.update_card(db, agent_a, card_id, {**card, "title": "Evidence edited card", "width": "full"})
    assert card_id not in {item["id"] for item in cards.list_cards(db, agent_b)}
    assert not cards.delete_card(db, agent_b, card_id)
    for call in (lambda: cards.duplicate_card(db, agent_b, card_id),
                 lambda: cards.update_card(db, agent_b, card_id, card)):
        try:
            call()
        except ValueError as error:
            assert str(error) == "That card no longer exists."
        else:
            raise AssertionError("Foreign card operation was accepted.")

    defaults = {item["seed_key"]: item for item in cards.list_cards(db, agent_a) if item["seed_key"]}
    removed_key = sorted(default_keys)[0]
    assert cards.delete_card(db, agent_a, defaults[removed_key]["id"])
    assert cards.delete_card(db, agent_a, duplicate_id)
    assert cards.seed_defaults(db, agent_a) == 0
    assert removed_key not in {item["seed_key"] for item in cards.list_cards(db, agent_a)}
    assert cards.restore_defaults(db, agent_a) == 1
    assert cards.restore_defaults(db, agent_a) == 0

    with closing(get_mongodb_client()) as reopened:
        persisted = {item["id"]: item for item in cards.list_cards(reopened[db.name], agent_a)}
    assert duplicate_id not in persisted and defaults[removed_key]["id"] not in persisted
    assert all(defaults[key]["id"] in persisted for key in default_keys - {removed_key})
    assert persisted[card_id]["title"] == "Evidence edited card" and persisted[card_id]["width"] == "full"
    assert {item["seed_key"] for item in persisted.values() if item["seed_key"]} == default_keys
    assert {item["seed_key"] for item in cards.list_cards(db, agent_b)} == default_keys
    fresh = fresh_app()
    login(fresh, EMAIL_A)
    page(fresh, "Analytics")
    assert any("Evidence edited card" in item.value for item in fresh.markdown)
    assert not any("Copy of Evidence custom card" in item.value for item in fresh.markdown)
    report(f"Analytics card CRUD and cross-agent restrictions on live MongoDB, fresh client and AppTest session persistence, and {len(default_keys)} defaults seeded once with one deleted default restored")


def verify_admin_flat_ui(app):
    click(app, "Log out")
    login(app, ADMIN_EMAIL)
    page(app, "Flat records")
    assert any("Administrator access" in item.value for item in app.caption)
    app.number_input(key="create_area").set_value(80.25)
    click(app, "Create flat")
    assert any(item.value == "Flat record created." for item in app.success)
    app.radio(key="flat_management_action").set_value("Update").run()
    app.number_input(key="edit_flat_search_id").set_value(2)
    click(app, "Find record")
    app.number_input(key="edit_2_area").set_value(81.35)
    click(app, "Save changes")
    assert any(item.value == "Flat record updated." for item in app.success)
    with closing(get_mysql_connection()) as connection:
        assert repository.get_flat(connection, 2)["floor_area_sqm"] == Decimal("81.35")
    report("Provisioned administrator used Streamlit to create and update a shared flat; DECIMAL area persisted in MySQL")


def verify_sql():
    rejected_queries = (
        "UPDATE resale_transaction SET resale_price = 1",
        "SELECT password_hash FROM agents",
        "SELECT 1; SELECT 2",
        "SELECT 1 /* comment */",
    )
    with closing(get_mysql_connection()) as connection, connection.cursor(buffered=True) as cursor:
        for query in rejected_queries:
            try:
                analytics_sql.run_query(connection, query)
            except analytics_sql.QueryRejected:
                assert not connection.in_transaction
            else:
                raise AssertionError("Unsafe SQL was accepted.")
        frame, truncated = analytics_sql.run_query(connection, "SELECT COUNT(*) AS sale_count FROM resale_transaction")
        assert list(frame["sale_count"]) == [0] and not truncated and not connection.in_transaction
        cursor.execute("SELECT @@session.max_execution_time")
        assert cursor.fetchone() == (analytics_sql.TIMEOUT_MS,)
    report("Live connection rejected four representative unsafe analytics statements and ran a safe SELECT with the configured timeout and rollback")


def main():
    start = perf_counter()
    os.environ["FLAT_RECORD_ADMIN_EMAIL"] = ADMIN_EMAIL
    with disposable_schema(), disposable_mongo() as db:
        os.environ["MONGODB_DATABASE"] = db.name
        seed_relational_fixture()
        searches.ensure_index(db)
        app = fresh_app()
        agent_a = verify_registration(app)
        verify_transactions(app, agent_a)
        search_id = verify_saved_search_ui(app, db, agent_a)
        agent_b = verify_isolation(app, db, agent_a, search_id)
        verify_dashboard(app, db, agent_a, agent_b)
        verify_admin_flat_ui(app)
        verify_sql()
    print(f"Functional evidence completed in {perf_counter() - start:.3f} s. Fixtures removed.")


if __name__ == "__main__":
    main()
