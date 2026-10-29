import time
import mysql.connector
import pandas as pd

# --- Database Configuration ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "musRootPw",
    "database": "mydb",
}


def main():
    start_total = time.time()

    # Connect to MySQL database
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # Disable foreign key checks temporarily for smooth bulk insertion
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        conn.commit()

        # ==========================================
        # 1. IMPORT INTO 'place'
        # ==========================================
        print("Importing into 'place' table...")
        start_table = time.time()

        place_df = pd.read_csv(
           "places_for_mysql.csv"
        )
        place_query = """
            INSERT INTO place (block_id, block_number, road_name, postal, latitude, longtitude, town)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE block_id=block_id;
        """
        place_data = [
            (
                int(row["block_id"]),
                str(row["block_number"]),
                str(row["road_name"]),
                str(row["postal"]),
                float(row["latitude"]),
                float(row["longitude"]),
                str(row["town"]),
            )
            for _, row in place_df.iterrows()
        ]

        cursor.executemany(place_query, place_data)
        conn.commit()
        place_time = time.time() - start_table
        print(
            f"-> 'place' imported {len(place_data)} rows in {place_time:.2f} seconds."
        )

        # ==========================================
        # 2. CREATE DEPENDENCIES ('nosql' & 'agents')
        # ==========================================
        print("Inserting default John Doe agent dependencies...")
        start_table = time.time()

        # Insert parent nosql record first to satisfy agents foreign key constraint
        cursor.execute(
            "INSERT IGNORE INTO nosql (idNoSQL, NoSQLData) VALUES (1, '{}');"
        )

        # Insert John Doe agent
        agent_query = """
            INSERT INTO agents (agent_id, name, email, phone_number, password_hash, NoSQL_idNoSQL)
            VALUES (1, 'John Doe', 'john_doe@example.com', '91234567', 'placeholder_hash', 1)
            ON DUPLICATE KEY UPDATE agent_id=agent_id;
        """
        cursor.execute(agent_query)
        conn.commit()
        agent_time = time.time() - start_table
        print(f"-> Default agent 'John Doe' set up in {agent_time:.2f} seconds.")

        # ==========================================
        # 3. IMPORT INTO 'flat'
        # ==========================================
        print("Importing into 'flat' table...")
        start_table = time.time()

        hdb_df = pd.read_csv("hdb_resale_enriched_block_id.csv")
        flat_query = """
            INSERT INTO flat (flat_type, flat_model, storey_range, floor_area_sqm, block_id, lease_commence_date, remaining_lease_months)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        flat_data = [
            (
                str(row["flat_type"]),
                str(row["flat_model"]),
                str(row["storey_range"]),
                int(row["floor_area_sqm"]),
                int(row["block_id"]),
                int(row["lease_commence_date"]),
                int(row["remaining_lease_months"]),
            )
            for _, row in hdb_df.iterrows()
        ]

        # Batch insert for large dataset in chunks of 10,000 rows
        chunk_size = 10000
        for i in range(0, len(flat_data), chunk_size):
            cursor.executemany(
                flat_query, flat_data[i : i + chunk_size]
            )
            conn.commit()

        flat_time = time.time() - start_table
        print(
            f"-> 'flat' imported {len(flat_data)} rows in {flat_time:.2f} seconds."
        )

        # Retrieve generated flat_ids to map to resale_transaction accurately
        cursor.execute("SELECT flat_id FROM flat ORDER BY flat_id ASC;")
        flat_ids = [row[0] for row in cursor.fetchall()]

        # ==========================================
        # 4. IMPORT INTO 'stations'
        # ==========================================
        print("Importing into 'stations' table...")
        start_table = time.time()

        mrt_df = pd.read_csv("mrt_lrt_full_list.csv")
        stations_query = """
            INSERT INTO stations (station_code, station_name, line_name, line_color, transport_type, place_block_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE station_code=station_code;
        """
        stations_data = [
            (
                str(row["ALPHANUMERIC_CODE"]),
                str(row["STATION_NAME_ENGLISH"]),
                str(row["LINE_ENGLISH"]),
                str(row["LINE_COLOR"]),
                str(row["TRANSPORT_TYPE"]),
                int(row["block_id"]),
            )
            for _, row in mrt_df.iterrows()
        ]

        cursor.executemany(stations_query, stations_data)
        conn.commit()
        stations_time = time.time() - start_table
        print(
            f"-> 'stations' imported {len(stations_data)} rows in {stations_time:.2f} seconds."
        )

        # ==========================================
        # 5. IMPORT INTO 'resale_transaction'
        # ==========================================
        print("Importing into 'resale_transaction' table...")
        start_table = time.time()

        resale_query = """
            INSERT INTO resale_transaction (FLAT_flat_id, AGENTS_agent_id, transacton_date, resale_price)
            VALUES (%s, %s, %s, %s);
        """
        
        resale_data = []
        for idx, row in hdb_df.iterrows():
            f_id = flat_ids[idx]
            
            # Parse '01-2017' and shift to the last day of that month (e.g., '2017-01-31')
            raw_date = str(row["transaction_date"]) # e.g. "01-2017"
            dt = pd.to_datetime(raw_date, format="%m-%Y")
            # Shift to the last day of the month
            end_of_month = dt + pd.offsets.MonthEnd(0)
            t_date = end_of_month.strftime("%Y-%m-%d")
            
            price = float(row["resale_price"])
            resale_data.append((f_id, 1, t_date, price))

        for i in range(0, len(resale_data), chunk_size):
            cursor.executemany(
                resale_query, resale_data[i : i + chunk_size]
            )
            conn.commit()

        resale_time = time.time() - start_table
        print(
            f"-> 'resale_transaction' imported {len(resale_data)} rows in {resale_time:.2f} seconds."
        )

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()

        total_time = time.time() - start_total
        print("\n==========================================")
        print(
            f"Total import time for all tables combined: {total_time:.2f} seconds."
        )
        print("==========================================")

    except Exception as e:
        conn.rollback()
        print(f"Error during import: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()