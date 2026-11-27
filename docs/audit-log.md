# Add a toggleable audit log

An acknowledgement is the message an agent sees after an action. A durable audit log is the database history of committed changes. For example, **Draft added** reports a change to the current Streamlit session. A sale appears in the audit history when MySQL commits the sale and its audit entry together.

Start with **My resale transactions**. The recorder below accepts events for any feature. Each repository supplies the actor, record key, action, and fields worth keeping. The repository still controls the transaction.

## 1. Create the audit table

Add this statement to [`setup/firstver_database.sql`](../setup/firstver_database.sql) after `resale_transaction` and before `SET SQL_MODE=@OLD_SQL_MODE`. For an existing installation, put the same statement in `setup/add_audit_log.sql` and execute that file once against your configured MySQL schema. The statement is safe to rerun and leaves the history empty until the first audited action.

```sql
CREATE TABLE IF NOT EXISTS `audit_event` (
    `event_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `occurred_at_utc` DATETIME(6) NOT NULL,
    `actor_agent_id` INT NOT NULL,
    `entity_type` VARCHAR(40) NOT NULL,
    `entity_key` VARCHAR(100) NOT NULL,
    `action` VARCHAR(20) NOT NULL,
    `before_data` JSON NULL,
    `after_data` JSON NULL,
    PRIMARY KEY (`event_id`),
    INDEX `ix_audit_actor_entity_event` (`actor_agent_id`, `entity_type`, `event_id`)
) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4;
```

In MySQL Workbench, select your configured database and run the file. From PowerShell, open the MySQL client with the schema account and run `SOURCE setup/add_audit_log.sql` at its prompt.

```powershell
mysql --host=localhost --port=3306 --user=YOUR_SCHEMA_USER -p --database=estateRecordsDB
```

The keys on the event are historical identifiers. The history survives deletion of the recorded sale. Keep writes append-only by granting the runtime user `INSERT` and `SELECT` on `audit_event`, and use a separate account for schema administration. Check the runtime user's `SHOW GRANTS` for broader privileges that would also allow audit edits or deletion.

## 2. Add the recording switch and recorder class

Add `ESTATE_AUDIT_ENABLED=0` to `.env.example` and your local `.env`. An operator can set it to `1` and restart Streamlit after the table and permissions are ready. This switch controls future recording for the whole app. The viewer in Step 5 has its own toggle for showing saved history.

Create `app/audit.py`.

```python
import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    actor_agent_id: int
    entity_type: str
    entity_key: str
    action: str
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AuditRecorder:
    enabled: bool

    @classmethod
    def from_environment(cls) -> "AuditRecorder":
        return cls(enabled=os.getenv("ESTATE_AUDIT_ENABLED", "0") == "1")

    def record(self, cursor: Any, event: AuditEvent) -> None:
        if not self.enabled:
            return

        cursor.execute(
            "INSERT INTO `audit_event` "
            "(occurred_at_utc, actor_agent_id, entity_type, entity_key, action, "
            "before_data, after_data) VALUES (UTC_TIMESTAMP(6), %s, %s, %s, %s, %s, %s)",
            (
                event.actor_agent_id,
                event.entity_type,
                event.entity_key,
                event.action,
                json.dumps(event.before, allow_nan=False) if event.before is not None else None,
                json.dumps(event.after, allow_nan=False) if event.after is not None else None,
            ),
        )
```

The class takes the repository's cursor. Its insert participates in that cursor's transaction. Keep your choice of fields in the feature repository. Exclude credentials, contact details, and raw user-supplied SQL from the event payloads.

## 3. Record the sale changes in their existing transaction

In [`app/repository.py`](../app/repository.py), import `AuditEvent` and `AuditRecorder` from `app.audit`. Add these two helpers immediately after `_INSERT_AGENT_TRANSACTION`. Reading the stored row gives you the actual date and decimal price MySQL accepted. The update and delete paths lock the old row while taking the before snapshot.

```python
def _transaction_snapshot(
    cursor: Any, agent_id: int, flat_id: int, *, lock: bool = False
) -> dict[str, object] | None:
    query = (
        "SELECT FLAT_flat_id, transaction_date, resale_price FROM `resale_transaction` "
        "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s"
    )
    cursor.execute(query + (" FOR UPDATE" if lock else ""), (flat_id, agent_id))
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "flat_id": row[0],
        "transaction_date": row[1].isoformat(),
        "resale_price": str(row[2]),
    }


def _record_resale_change(
    cursor: Any,
    recorder: AuditRecorder,
    agent_id: int,
    flat_id: int,
    action: str,
    *,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> None:
    recorder.record(cursor, AuditEvent(
        actor_agent_id=agent_id,
        entity_type="resale_transaction",
        entity_key=f"{agent_id}:{flat_id}",
        action=action,
        before=before,
        after=after,
    ))
```

1. Replace the body of `create_agent_transaction` with the code below.

   ```python
   recorder = AuditRecorder.from_environment()
   try:
       with connection.cursor(buffered=True) as cursor:
           cursor.execute(
               _INSERT_AGENT_TRANSACTION,
               (flat_id, agent_id, transaction_date, Decimal(str(resale_price))),
           )
           if recorder.enabled:
               _record_resale_change(
                   cursor, recorder, agent_id, flat_id, "create",
                   after=_transaction_snapshot(cursor, agent_id, flat_id),
               )
       connection.commit()
   except Exception:
       connection.rollback()
       raise
   ```

2. In `create_agent_transactions_batch`, add `recorder = AuditRecorder.from_environment()` before `connection.start_transaction()`, and change the cursor to `connection.cursor(buffered=True)`. Insert these lines immediately after the existing `cursor.execute(_INSERT_AGENT_TRANSACTION, parameters)`, inside the loop. This writes one audit event per committed sale. Keep the existing single commit and rollback around the whole loop.

   ```python
   if recorder.enabled:
       flat_id = draft["flat_id"]
       _record_resale_change(
           cursor, recorder, agent_id, flat_id, "create",
           after=_transaction_snapshot(cursor, agent_id, flat_id),
       )
   ```

3. Replace the body of `update_agent_transaction` with the code below. A successful save of identical values still returns `True`. Only changed rows create an event. When the flat ID changes, `entity_key` records the new key and the old flat ID is in `before_data`.

   ```python
   recorder = AuditRecorder.from_environment()
   try:
       with connection.cursor(buffered=True) as cursor:
           before = (
               _transaction_snapshot(cursor, agent_id, original_flat_id, lock=True)
               if recorder.enabled else None
           )
           if recorder.enabled and before is None:
               connection.rollback()
               return False
           cursor.execute(
               "UPDATE `resale_transaction` "
               "SET FLAT_flat_id = %s, transaction_date = %s, resale_price = %s "
               "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
               (flat_id, transaction_date, Decimal(str(resale_price)), original_flat_id, agent_id),
           )
           changed = cursor.rowcount > 0
           if changed and recorder.enabled:
               _record_resale_change(
                   cursor, recorder, agent_id, flat_id, "update", before=before,
                   after=_transaction_snapshot(cursor, agent_id, flat_id),
               )
           found = changed or before is not None
           if not found:
               cursor.execute(
                   "SELECT FLAT_flat_id FROM `resale_transaction` "
                   "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
                   (original_flat_id, agent_id),
               )
               found = cursor.fetchone() is not None
       connection.commit()
   except Exception:
       connection.rollback()
       raise
   return found
   ```

4. Replace the body of `delete_agent_transaction` with the code below. The event's `before_data` preserves the details after deletion.

   ```python
   recorder = AuditRecorder.from_environment()
   try:
       with connection.cursor(buffered=True) as cursor:
           before = (
               _transaction_snapshot(cursor, agent_id, flat_id, lock=True)
               if recorder.enabled else None
           )
           if recorder.enabled and before is None:
               connection.rollback()
               return False
           cursor.execute(
               "DELETE FROM `resale_transaction` "
               "WHERE FLAT_flat_id = %s AND AGENTS_agent_id = %s",
               (flat_id, agent_id),
           )
           deleted = cursor.rowcount > 0
           if deleted and recorder.enabled:
               _record_resale_change(cursor, recorder, agent_id, flat_id, "delete", before=before)
       connection.commit()
   except Exception:
       connection.rollback()
       raise
   return deleted
   ```

Keep the single-record writes on the existing connection. Their UI can already have an implicit transaction from a read, and the batch opens a fresh connection for its explicit `start_transaction()`. Each write reports success to the UI after `commit()` returns. An audit insert failure rolls back the sale when recording is enabled. Adding, editing, or removing a session draft only needs the existing UI feedback.

## 4. Keep history private from Analytics SQL

The Analytics page executes user-written `SELECT` with shared MySQL credentials today. Give it a separate account with grants on the existing analytics tables before enabling the audit feature. Run the following as a schema administrator and substitute the actual schema, the account host, and a locally generated password.

```sql
CREATE USER 'estate_analytics'@'localhost' IDENTIFIED BY 'REPLACE_WITH_GENERATED_PASSWORD';
GRANT SELECT ON `estateRecordsDB`.`place` TO 'estate_analytics'@'localhost';
GRANT SELECT ON `estateRecordsDB`.`flat` TO 'estate_analytics'@'localhost';
GRANT SELECT ON `estateRecordsDB`.`stations` TO 'estate_analytics'@'localhost';
GRANT SELECT ON `estateRecordsDB`.`nearby` TO 'estate_analytics'@'localhost';
GRANT SELECT ON `estateRecordsDB`.`resale_transaction` TO 'estate_analytics'@'localhost';
```

1. Add `ANALYTICS_MYSQL_USER=estate_analytics` and `ANALYTICS_MYSQL_PASSWORD=YOUR_GENERATED_PASSWORD` to `.env`. Put placeholders in `.env.example`.
2. In [`app/app_modules/database/database.py`](../app/app_modules/database/database.py), change the factory signature to `def get_mysql_connection(*, analytics: bool = False):`. Set `credential_prefix = "ANALYTICS_MYSQL" if analytics else "MYSQL"`, then read `os.getenv(f"{credential_prefix}_USER")` and `os.getenv(f"{credential_prefix}_PASSWORD")`. Keep the existing database, host, and port settings, and update the missing-credentials message to reference the selected prefix.
3. In [`app/workspace_pages/analytics_ui.py`](../app/workspace_pages/analytics_ui.py), change the `get_mysql_connection()` calls in `run_card_query` and `filter_values` to `get_mysql_connection(analytics=True)`. Add `audit_event` to `_BLOCKED_IDENTIFIERS` in [`analytics_sql.py`](../app/app_modules/analytics/analytics_sql.py) for a clearer message. MySQL grants enforce the boundary.
4. Sign in to MySQL as the analytics account. Check `SHOW GRANTS`, run a normal query against `resale_transaction`, and confirm that a query against `audit_event` gets a permission error. Test the existing builder cards afterwards.

## 5. Add the history viewer toggle

Add this function to `app/audit.py`. It uses a bound actor ID from the logged-in session, limits the number of rows, and keeps its scope on one feature.

```python
def list_agent_history(
    connection: Any, agent_id: int, entity_type: str
) -> list[dict[str, Any]]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT occurred_at_utc, entity_key, action, before_data, after_data "
            "FROM `audit_event` WHERE actor_agent_id = %s AND entity_type = %s "
            "ORDER BY event_id DESC LIMIT 100",
            (agent_id, entity_type),
        )
        return cursor.fetchall()
```

Import `list_agent_history` in [`app/workspace_pages/transactions_ui.py`](../app/workspace_pages/transactions_ui.py). Add the following after `st.subheader("My resale transactions")` in `render_agent_transactions`. The existing `closing` and `get_mysql_connection` imports apply. Refreshing the page reads the history again. Switching recording off leaves previously recorded entries available here.

```python
if st.toggle("Show change history", key=f"show_resale_history_{agent_id}"):
    with closing(get_mysql_connection()) as connection:
        events = list_agent_history(connection, agent_id, "resale_transaction")
    if events:
        st.caption("Latest 100 changes, with timestamps in UTC.")
        st.dataframe(events, hide_index=True, width="stretch")
    else:
        st.info("No recorded changes for your account yet.")
```

For a cleaner table, use `st.column_config` to label the fields **Time (UTC)**, **Record**, **Action**, **Before**, and **After**. Use the logged-in `agent_id` for every history request. A global viewer would need its own server-side permission check.

## 6. Verify the behaviour before enabling recording

Use a disposable MySQL schema for this walkthrough. The integration tests already build and drop temporary schemas from `firstver_database.sql`. Use a regular test account and test flats, then check the following.

| Action | Expected result |
| --- | --- |
| Save with `ESTATE_AUDIT_ENABLED=0` | The sale saves with zero new events. |
| Add or edit a draft with recording on | The UI acknowledges the draft with zero new events. |
| Commit two valid drafts | A new MySQL session sees two new sales and two matching create events. |
| Commit a valid draft followed by a duplicate | A new session sees zero new sales and zero new events for that batch. |
| Save a changed price and then save that same price again | One update event shows the before and after prices. |
| Delete a sale | The history shows its old price and date, and its after value is empty. |
| Set recording off again | Older entries still appear when the viewer is open. |
| Sign in as a second agent | The history is scoped to that agent. |

Extend the two existing batch tests in [`test/test_mysql_schema.py`](../test/test_mysql_schema.py). Import `patch` from `unittest.mock`, then add this helper to `MySQLSchemaTests`. Each call reads from a separate connection, like `committed_transactions`.

```python
def committed_audit_events(self):
    with closing(get_mysql_connection()) as observer:
        observer.database = self.schema
        with observer.cursor() as cursor:
            cursor.execute(
                "SELECT actor_agent_id, entity_key, action, "
                "JSON_UNQUOTE(JSON_EXTRACT(after_data, '$.resale_price')) "
                "FROM audit_event ORDER BY event_id"
            )
            return cursor.fetchall()
```

In the successful batch test, wrap the repository call in the patch and add the event assertion alongside the existing sale assertions. Leave `load_batch_fixture` outside the patch so its seed sale creates no audit event.

```python
with patch.dict(os.environ, {"ESTATE_AUDIT_ENABLED": "1"}):
    self.assertEqual(repository.create_agent_transactions_batch(self.connection, 1, items), 2)
self.assertEqual(self.committed_audit_events(), [
    (1, "1:2", "create", "520000.23"),
    (1, "1:3", "create", "550000.47"),
])
```

In the failing batch test, put the same environment patch around `self.assertRaises` and the repository call inside each `subTest`. Add `self.assertEqual(self.committed_audit_events(), [])` after the existing committed-sale assertion. To test a broken recorder, patch `AuditRecorder.record` with `side_effect=mysql.connector.Error("Audit write failed")` and attempt a single create with recording enabled. Check that the exception reaches the caller and the attempted sale is absent from `committed_transactions()`.

```powershell
$env:ESTATE_AUDIT_ENABLED = '0'
$env:ESTATE_MYSQL_TEST = '1'
.\.venv\Scripts\python.exe -m unittest discover -s test -v
Remove-Item Env:ESTATE_MYSQL_TEST,Env:ESTATE_AUDIT_ENABLED
```

## 7. Extend the same design to other features

For an administrator editing a flat, pass the signed-in administrator's `agent_id` to the flat repository. Take allowlisted snapshots of fields such as `flat_type` and `floor_area_sqm`. Serialize decimals as strings, then call `recorder.record(cursor, AuditEvent(actor_id, "flat", str(flat_id), "update", before, after))` before the flat update commits. Read `cursor.lastrowid` immediately after a flat insert and use it as the new event's key. The event type and key let the same recorder handle both features.

Saved searches and analytics cards are MongoDB writes. Give MongoDB its own recorder with the same event fields if you add history there. For a separate event collection with atomic writes, run the document write and event insert in one MongoDB session transaction on a deployment configured for transactions. Verify both commits and rollbacks in that deployment before enabling the feature. Writing a MongoDB action's history to MySQL in a second request has an independent commit and can leave the action and its history out of sync.
