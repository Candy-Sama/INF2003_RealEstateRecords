# INF2003 Real Estate Records

A Streamlit application for property agents to manage HDB flat records, search
resale transaction history, and save search criteria. MySQL stores agent and
property data; MongoDB stores each agent's saved searches.

## Application flows

- **Register / log in:** agent accounts use the MySQL `agents` table. Passwords
  are stored as salted scrypt hashes, never as plain text.
- **Manage flats:** create, list, update, and delete records in `flat`, linked to
  locations in `place`. Foreign keys can prevent deleting flats with transactions.
- **Search / filter:** search `resale_transaction`, joined to `flat` and `place`,
  by town, flat type, price range, and transaction date. Results are limited to
  1,000 records.
- **Saved searches:** MongoDB's `saved_searches` collection stores each search's
  name, criteria, and MySQL `agent_id`. Agents can run, rename, and delete their
  own saved searches.

## Configure and run locally

1. Start your local MySQL and MongoDB servers.
2. Create and activate a Python virtual environment.
   ```powershell
      python -m venv .venv
      .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Create your local environment file from the example:

   ```powershell
   Copy-Item .env.example .env
   ```

   Edit `.env` and set `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` to
   your MySQL schema and credentials. Change the MongoDB settings if your local
   server differs from the defaults.

5. Launch the application:

   ```powershell
   streamlit run app.py
   ```

`database.py` loads `.env` from the project directory. Environment variables
already set by your shell or deployment take precedence over values in `.env`.
The real `.env` file is ignored by Git; do not commit credentials.

## Tests

Run the local unit tests with:

```powershell
python -m unittest test_repository test_security
```

`test_repository.py` checks that transaction search filters are passed to SQL
as parameters rather than inserted into the query text. It uses a fake
connection, so it does not connect to or change your MySQL database.
`test_security.py` checks password hashing and verification locally. These
tests do not start the app, connect to either database, or affect normal use.

## Expected MySQL schema

The queries follow the names and columns visible in the supplied ER diagram:

- `agents`: `agent_id`, `name`, `email`, `phone_number`, `password_hash`
- `flat`: `flat_id`, `flat_type`, `flat_model`, `storey_range`,
  `floor_area_sqm`, `block_id`, `lease_commence_date`,
  `remaining_lease_months`
- `place`: `block_id`, `block_number`, `road_name`, `postal`, `town`
- `resale_transaction`: `FLAT_flat_id`, `AGENTS_agent_id`,
  `transaction_date`, `resale_price`

`agent_id` and `flat_id` are expected to be auto-generated primary keys. Email
should have a unique constraint. `agents.password_hash` should hold at least 100
characters (the scrypt hash is 86 characters).

The `nosql` box in the EER drawing is illustrative, not a MySQL table. You do
not need a `NoSQL_idNoSQL` column in `agents` for this design. Each saved-search
document in MongoDB stores the owning MySQL `agent_id`; the app uses that value
to retrieve only the signed-in agent's saved searches. This is an application-
level reference, not a relational foreign key between MySQL and MongoDB.

## Notes

Database names and exact column constraints were not visible in the diagram.
Set `MYSQL_DATABASE` to your schema name and adjust the SQL in `repository.py`
if your physical schema differs. The app does not create or migrate database
tables automatically.
