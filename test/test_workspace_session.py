import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from streamlit.testing.v1 import AppTest

from app import repository
from app.app_modules import authentication_ui
from app.app_modules.database import database


class WorkspaceSessionTests(unittest.TestCase):
    def test_logout_clears_workspace_before_another_agent_signs_in(self) -> None:
        app_file = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
        connection = Mock()
        mongo_client = MagicMock()
        agents = [
            {
                "agent_id": agent_id,
                "name": name,
                "email": f"{name.lower()}@example.com",
                "password_hash": "test-only",
            }
            for agent_id, name in [(1, "Alice"), (2, "Bob")]
        ]

        with (
            patch.object(database, "get_mysql_connection", return_value=connection),
            patch.object(authentication_ui, "get_mysql_connection", return_value=connection),
            patch.object(database, "get_mongodb_client", return_value=mongo_client),
            patch.object(authentication_ui, "verify_password", return_value=True),
            patch.object(repository, "find_agent_by_email", side_effect=agents),
            patch.object(repository, "list_towns", return_value=["Tampines"]),
            patch.object(repository, "list_flat_types", return_value=["4 ROOM"]),
            patch.object(repository, "search_transactions", return_value=[{"flat_id": 42}]) as search,
        ):
            app = AppTest.from_file(str(app_file)).run()
            self.sign_in(app, "alice@example.com")

            app.selectbox(key="filter_town").select("Tampines")
            self.click(app, "Search records")
            self.assertEqual(len(app.dataframe), 1)
            self.assertEqual(app.session_state["last_search_filters"]["town"], "Tampines")
            app.session_state["an_editor"] = {"id": "alice-card"}
            app.session_state["transaction_batch_1"] = [{"flat_id": 42}]

            self.click(app, "Log out")
            for key in (
                "agent", "last_search_filters", "last_search_results", "an_editor", "transaction_batch_1",
            ):
                with self.subTest(key=key):
                    self.assertNotIn(key, app.session_state)

            self.sign_in(app, "bob@example.com")
            self.assertEqual(app.session_state["agent"]["agent_id"], 2)
            self.assertEqual(app.selectbox(key="filter_town").value, "Any")
            self.assertFalse(app.dataframe)
            search.assert_called_once()

    def sign_in(self, app: AppTest, email: str) -> None:
        next(widget for widget in app.text_input if widget.label == "Email address").input(email)
        next(widget for widget in app.text_input if widget.label == "Password").input("test-password")
        self.click(app, "Log in")

    def click(self, app: AppTest, label: str) -> None:
        next(button for button in app.button if button.label == label).click().run()
        self.assertFalse(app.exception)
