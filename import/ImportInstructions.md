# How to import the data

## Prequisite
Have the 3 csv files and import.py in the same folder. Change the database config respectively.

## Step by step

1. Download the 3 csv files: `hdb_resale_enriched_block_id.csv`, `mrt_lrt_full_list.csv` and `places_for_mysql.csv`
2. Downlaod `import.py` in the same folder as the 3 csv files
3. Install dependencies:

   ```
   pip install pandas mysql-connector-python
   ```
4. Change the database config (Usually your password but other change other stuff if relevant)
3. Run the import.py program

# How it works & Output
Import.py would import the csv data into their respective mysql tables, starting with place from `places_for_mysql.csv`, creating a default John Doe agent in agents folder for dependency, import into flat table with `hdb_resale_enriched_block_id.csv` and lastly import into stations table with `mrt_lrt_full_list.csv`. Total import time for each table would be shown followed by the total output time for all the tables.