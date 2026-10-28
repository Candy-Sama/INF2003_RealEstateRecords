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
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Configure the MySQL connection in PowerShell (replace values for your setup):

   ```powershell
   $env:MYSQL_HOST = "localhost"
   $env:MYSQL_PORT = "3306"
   $env:MYSQL_DATABASE = "mydb"
   $env:MYSQL_USER = "root"
   $env:MYSQL_PASSWORD = "your_mysql_password"
   ```

5. Configure MongoDB if it differs from the defaults (`mongodb://localhost:27017`
   and database `estate_records`):

   ```powershell
   $env:MONGODB_URI = "mongodb://localhost:27017"
   $env:MONGODB_DATABASE = "estate_records"
   ```

6. Launch the application:

   ```powershell
   streamlit run app.py
   ```

The variables set in PowerShell apply to that terminal session. Keep credentials
out of source control; configure them as environment variables in your deployment
environment as well.

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

The diagram also shows `agents.NoSQL_idNoSQL` referencing a relational `nosql`
table. Since this app stores saved searches directly in MongoDB, its MongoDB
documents use `agent_id` as their owner key instead. For registration to work,
make `NoSQL_idNoSQL` nullable or give it a default, and ensure the
`agents` insert does not require a separate `nosql` row. Do not try to enforce a
MySQL foreign key to a MongoDB document.

## Notes

Database names and exact column constraints were not visible in the diagram.
Set `MYSQL_DATABASE` to your schema name and adjust the SQL in `repository.py`
if your physical schema differs. The app does not create or migrate database
tables automatically.
