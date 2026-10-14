# INF2003 Real Estate Records

Property agents assisting clients in purchasing HDB resale flats may need to compare large amounts of historical transaction and location data while considering factors such as price, flat age, room type and MRT accessibility. We propose an application that assists property agents in identifying suitable HDB resale locations and blocks based on their clients’ requirements. Agents will be able to specify criteria such as desired flat type, budget and location preferences, and the system will retrieve and compare relevant resale transaction records to support their recommendations. 

## Run locally

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the app:

   ```powershell
   streamlit run app.py
   ```

## Database integration

The app does not connect to a database or store account information yet. Add
connection configuration and implementations in `database.py`, then wire the
login and registration form handlers in `app.py` to your authentication logic.
Use MySQL for relational data such as user accounts and property records, and
MongoDB for document-oriented data such as saved searches.

Before enabling registration, store passwords using a dedicated password-hashing
algorithm; never store plain-text passwords. Keep database credentials outside
the source code, for example in Streamlit secrets or environment variables.
