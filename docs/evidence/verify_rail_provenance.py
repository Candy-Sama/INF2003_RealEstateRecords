"""Compare the downloaded Kaggle files, team archives and bundled import inputs."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from io import StringIO, TextIOWrapper
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
IMPORT = ROOT / "setup" / "import_data_script"
RAIL = "mrt_lrt_full_list.csv"
SALES = "hdb_resale_enriched_block_id.csv"
PLACES = "places_for_mysql.csv"
COORDINATES = ("LATITUDE", "LONGITUDE", "X", "Y")
STATION_PLACE_FIELDS = {
    "BLK_NO": "block_number", "ROAD_NAME": "road_name", "POSTAL": "postal",
    "LATITUDE": "latitude", "LONGITUDE": "longitude", "Town": "town",
}
HDB_PLACE_FIELDS = {
    "block_number": "block_number", "street_name": "road_name", "postal": "postal",
    "latitude": "latitude", "longitude": "longitude", "town": "town",
}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def csv_records(content):
    reader = csv.DictReader(StringIO(content.decode("utf-8-sig"), newline=""))
    return reader.fieldnames, list(reader)


def file_details(content, header, rows):
    return {"sha256": sha256(content), "bytes": len(content), "rows": len(rows), "columns": header}


def by_key(rows, column):
    keyed = {row[column]: row for row in rows}
    assert len(keyed) == len(rows)
    return keyed


def name_key(value):
    return " ".join(value.upper().split())


def decimal_coordinate(row, columns):
    return tuple(Decimal(row[column]) for column in columns)


def rounded_10(value):
    number = Decimal(value)
    return number.quantize(Decimal(1).scaleb(number.adjusted() - 9))


def rail_audit(sources, places):
    parsed = {name: csv_records(content) for name, content in sources.items()}
    source_b = parsed["kaggle_b_v1_TrainStationLocation.csv"][1]
    source_c = parsed["kaggle_c_v3_mrt_lrt_stations.csv"][1]
    dated = by_key(parsed["kaggle_c_v3_mrt_lrt_stations_2025-01-14.csv"][1], "code")
    raw_header, raw_rows = parsed["team_raw_mrt_lrt_full_list.csv"]
    final_header, final_rows = parsed["bundled_mrt_lrt_full_list.csv"]
    code = "ALPHANUMERIC_CODE"
    raw = by_key(raw_rows, code)
    final = by_key(final_rows, code)
    shared_codes = raw.keys() & final.keys()
    shared_fields = [field for field in raw_header if field in final_header]
    matches = {}
    source_keys = {(name_key(row["station_name"]), row["type"]): row for row in source_b}
    for key, row in final.items():
        candidate = source_keys.get((name_key(row["STATION_NAME_ENGLISH"]), row["TRANSPORT_TYPE"]))
        if candidate:
            matches[key] = candidate

    clean_rail = parsed["team_cleaned_mrt_stations_cleaned.csv"][1]
    raw_c_file = sources["team_raw_mrt_lrt_full_list.csv"]
    source_c_file = sources["kaggle_c_v3_mrt_lrt_stations.csv"]
    round_counts = {
        field: sum(rounded_10(raw[key][field]) == Decimal(final[key][field]) for key in shared_codes)
        for field in COORDINATES
    }
    jan_fields = {
        "station_name": "STATION_NAME_ENGLISH", "line": "LINE_ENGLISH", "color": "LINE_COLOR",
        "opening": "OPENING_DATE", "type": "TRANSPORT_TYPE", "blk_no": "BLK_NO",
        "road_name": "ROAD_NAME", "building": "BUILDING", "address": "ADDRESS", "postal": "POSTAL",
        "x": "X", "y": "Y", "latitude": "LATITUDE", "longitude": "LONGITUDE",
    }
    samples = []
    for key in ("NS1", "EW24", "NE1", "PE1", "TE1"):
        row = final[key]
        source_b_pair = matches.get(key)
        samples.append({
            "code": key, "name": row["STATION_NAME_ENGLISH"], "line": row["LINE_ENGLISH"].strip(),
            "color": row["LINE_COLOR"], "type": row["TRANSPORT_TYPE"], "place_id": int(row["block_id"]),
            "B_lat_lon": [source_b_pair["lat"], source_b_pair["lng"]] if source_b_pair else None,
            "C_legacy_lat_lon": [raw[key]["LATITUDE"], raw[key]["LONGITUDE"]],
            "bundled_lat_lon": [row["LATITUDE"], row["LONGITUDE"]],
            "C_legacy_postal": raw[key]["POSTAL"], "bundled_postal": row["POSTAL"],
            "bundled_town": row["Town"], "C_dated_planning_area": dated[key]["planning_area_ura"],
        })

    return {
        "files": {name: file_details(sources[name], *item) for name, item in parsed.items()},
        "B_archive_bytes_equal": sources["kaggle_b_v1_TrainStationLocation.csv"]
        == sources["team_raw_mrt_station_locations.csv"],
        "B_cleaned_matches_by_order_name_type_and_coordinates": sum(
            name_key(before["station_name"]) == after["station_name"]
            and before["type"] == after["transport_type"]
            and decimal_coordinate(before, ("lat", "lng"))
            == decimal_coordinate(after, ("latitude", "longitude"))
            for before, after in zip(source_b, clean_rail, strict=True)
        ),
        "cleaned_and_tracked_rail_sample_bytes_equal": sources["team_cleaned_mrt_stations_cleaned.csv"]
        == sources["tracked_mrt_stations_sample.csv"],
        "B_station_codes_joinable_by_normalized_name_type": len(matches),
        "B_unmatched_station_codes": sorted(final.keys() - matches.keys()),
        "B_exact_coordinate_pairs_in_C_legacy_by_name_type": sum(
            decimal_coordinate(raw[key], ("LATITUDE", "LONGITUDE"))
            == decimal_coordinate(candidate, ("lat", "lng")) for key, candidate in matches.items()
        ),
        "B_exact_coordinate_pairs_in_bundled_rail_by_name_type": sum(
            decimal_coordinate(final[key], ("LATITUDE", "LONGITUDE"))
            == decimal_coordinate(candidate, ("lat", "lng")) for key, candidate in matches.items()
        ),
        "C_legacy_archive_parsed_rows_equal": source_c == raw_rows,
        "C_legacy_archive_bytes_equal_after_newline_normalization": raw_c_file.replace(b"\r\n", b"\n")
        == source_c_file.replace(b"\r\n", b"\n"),
        "C_legacy_line_endings": {
            "archived_CRLF": raw_c_file.count(b"\r\n"), "downloaded_LF": source_c_file.count(b"\n"),
        },
        "C_legacy_and_bundled_same_codes_and_order": list(raw) == list(final),
        "C_legacy_unique_names": len({name_key(row["STATION_NAME_ENGLISH"]) for row in raw_rows}),
        "C_legacy_to_bundled_text_differences_per_shared_column": {
            field or "(unnamed index)": sum(raw[key][field] != final[key][field] for key in shared_codes)
            for field in shared_fields
        },
        "C_legacy_removed_columns": [field for field in raw_header if field not in final_header],
        "bundled_added_columns": [field for field in final_header if field not in raw_header],
        "bundled_coordinate_values_matching_C_legacy_at_10_significant_digits": round_counts,
        "max_absolute_numeric_coordinate_delta": {
            field: str(max(abs(Decimal(raw[key][field]) - Decimal(final[key][field])) for key in shared_codes))
            for field in COORDINATES
        },
        "bundled_opening_dates_matching_C_legacy_after_reformat": sum(
            date.fromisoformat(raw[key]["OPENING_DATE"])
            == date(*map(int, reversed(final[key]["OPENING_DATE"].split("/")))) for key in shared_codes
        ),
        "bundled_postal_values_matching_C_legacy_after_padding_to_six": sum(
            raw[key]["POSTAL"] == final[key]["POSTAL"].zfill(6) for key in shared_codes
        ),
        "bundled_station_postal_string_lengths": dict(Counter(len(row["POSTAL"]) for row in final_rows)),
        "bundled_station_town_equals_uppercase_station_name": sum(
            row["Town"] == row["STATION_NAME_ENGLISH"].upper() for row in final_rows
        ),
        "bundled_station_ids_match_source_order_starting_at_9762": sum(
            int(row["block_id"]) == position for position, row in enumerate(final_rows, 9762)
        ),
        "station_place_field_mismatches": {
            field: sum(row[source] != places[row["block_id"]][field] for row in final_rows)
            for source, field in STATION_PLACE_FIELDS.items()
        },
        "C_dated_codes_added": sorted(dated.keys() - raw.keys()),
        "C_dated_codes_missing_from_legacy": sorted(raw.keys() - dated.keys()),
        "C_dated_text_differences_from_legacy_for_shared_codes": {
            field: sum(dated[key][source] != raw[key][field] for key in raw.keys() & dated.keys())
            for source, field in jan_fields.items()
        },
        "C_dated_planning_area_matches_bundled_Town_ignoring_case": sum(
            name_key(dated[key]["planning_area_ura"]) == name_key(final[key]["Town"])
            for key in dated.keys() & final.keys()
        ),
        "representative_records": samples,
    }


def hdb_audit(raw_archive, cleaned_archive, places):
    raw_name = "hdb_resale_transactions.csv"
    cleaned_name = "cleaned_v2/hdb_resale_cleaned.csv"
    enriched_name = "cleaned_v2/hdb_resale_enriched.csv"
    filenames = (raw_name, cleaned_name, enriched_name, SALES)
    raw_fields = {"block": "block_number", "remaining_lease": "remaining_lease_raw",
                  **{key: key for key in ("street_name", "town", "flat_type", "flat_model",
                                          "storey_range", "lease_commence_date")}}
    uppercase_fields = {"street_name", "town", "flat_type", "flat_model"}
    differences = Counter()
    sale_fields = set(HDB_PLACE_FIELDS) | {"full_address", "block_id"}
    by_address = {}
    postal_lengths = Counter()
    max_delta = dict.fromkeys(("latitude", "longitude"), Decimal(0))
    with ExitStack() as files:
        streams = [raw_archive.open(raw_name), cleaned_archive.open(cleaned_name),
                   cleaned_archive.open(enriched_name), (IMPORT / SALES).open("rb")]
        readers = [csv.DictReader(files.enter_context(TextIOWrapper(stream, encoding="utf-8-sig", newline="")))
                   for stream in streams]
        for count, (raw, clean, enriched, sale) in enumerate(zip(*readers, strict=True), 1):
            differences["raw_to_cleaned_text"] += sum(raw[k] != clean[v] for k, v in raw_fields.items())
            differences["raw_to_cleaned_text_after_expected_normalization"] += sum(
                (raw[k].strip().upper() if k in uppercase_fields else raw[k]) != clean[v]
                for k, v in raw_fields.items()
            )
            differences["raw_to_cleaned_money_or_area"] += sum(
                Decimal(raw[k]) != Decimal(clean[k]) for k in ("resale_price", "floor_area_sqm")
            )
            differences["raw_to_cleaned_month"] += f'{raw["month"]}-01' != clean["transaction_date"]
            differences["block_street_address"] += clean["full_address"] != f'{raw["block"]} {raw["street_name"]}'
            differences["cleaned_to_enriched_cells"] += sum(clean[k] != enriched[k] for k in clean)
            differences["enriched_to_bundled_cells_excluding_dates_and_coordinates"] += sum(
                enriched[k] != sale[k] for k in clean if k != "transaction_date"
            )
            differences["enriched_to_bundled_month"] += (
                date.fromisoformat(enriched["transaction_date"]).strftime("%m-%Y") != sale["transaction_date"]
            )
            for axis in max_delta:
                delta = abs(Decimal(enriched[axis]) - Decimal(sale[axis]))
                differences[f"{axis}_changed"] += bool(delta)
                differences[f"{axis}_changed_not_10_significant_digits"] += (
                    bool(delta) and rounded_10(enriched[axis]) != Decimal(sale[axis])
                )
                max_delta[axis] = max(max_delta[axis], delta)
            address = sale["full_address"]
            existing = by_address.setdefault(address, {k: sale[k] for k in sale_fields})
            differences["inconsistent_block_id_for_sale_address"] += existing["block_id"] != sale["block_id"]

    for ordinal, address in enumerate(sorted(by_address), 1):
        sale = by_address[address]
        differences["hdb_block_id_differs_from_sorted_address_ordinal"] += int(sale["block_id"]) != ordinal
        postal_lengths[len(sale["postal"])] += 1
        place = places[sale["block_id"]]
        differences["hdb_place_projected_cells"] += sum(sale[k] != place[v] for k, v in HDB_PLACE_FIELDS.items())
    return {
        "sha256": dict(zip(filenames, map(sha256, (raw_archive.read(raw_name), cleaned_archive.read(cleaned_name),
                                                 cleaned_archive.read(enriched_name), (IMPORT / SALES).read_bytes())),
                           strict=True)),
        "rows_in_each_stage": count, "distinct_hdb_addresses": len(by_address),
        "difference_counts": dict(differences), "max_absolute_coordinate_delta": max_delta,
        "hdb_place_postal_string_lengths": dict(postal_lengths),
    }


def team_export_audit(used_data, rail_intermediate, places_file, rail_file):
    local_stages = (
        "hdb_resale_enriched.csv", "hdb_resale_enriched_with_postal.csv",
        "hdb_resale_enriched_with_postal_v2.csv", "hdb_resale_enriched__postal_v2_cleanup.csv", SALES,
    )
    nil_rows = Counter(dict.fromkeys(local_stages[1:], 0))
    nil_addresses = {name: set() for name in local_stages[1:]}
    zero_stripped_addresses = set()
    date_formats = {}
    changes = Counter()
    with ExitStack() as resources:
        readers = [csv.DictReader(resources.enter_context((used_data / name).open(
            encoding="utf-8-sig", newline=""))) for name in local_stages]
        for count, rows in enumerate(zip(*readers, strict=True), 1):
            for name, row in zip(local_stages, rows, strict=True):
                if count == 1:
                    date_formats[name] = row["transaction_date"]
                if row.get("postal") == "NIL":
                    nil_rows[name] += 1
                    nil_addresses[name].add(row["full_address"])
                changes["hdb_stage_address_mismatch"] += row["full_address"] != rows[0]["full_address"]
            geocoded, first, v2, cleanup, final = rows
            changes["first_to_v2_NIL_rows_filled"] += first["postal"] == "NIL" and v2["postal"] != "NIL"
            changes["first_to_v2_existing_postals_changed"] += (
                first["postal"] != "NIL" and first["postal"] != v2["postal"]
            )
            changes["v2_to_cleanup_NIL_rows_filled"] += v2["postal"] == "NIL" and cleanup["postal"] != "NIL"
            changes["v2_to_cleanup_existing_postals_changed"] += (
                v2["postal"] != "NIL" and v2["postal"] != cleanup["postal"]
            )
            changes["cleanup_to_final_postal_text_changes"] += cleanup["postal"] != final["postal"]
            if cleanup["postal"] != final["postal"] and cleanup["postal"].lstrip("0") == final["postal"]:
                changes["cleanup_to_final_postals_only_lose_leading_zero"] += 1
                zero_stripped_addresses.add(cleanup["full_address"])
            changes["original_block_id_differs_from_final"] += geocoded["block_id"] != final["block_id"]

    team_places = (used_data / PLACES).read_bytes()
    _, team_place_rows = csv_records(team_places)
    _, bundled_place_rows = csv_records(places_file)
    hashes = local_stages + (PLACES, RAIL, "postal.py", "postal_cleanup.py", "blocks.py", "blocks_check.py",
                             "place.py", "import.py")
    result = {
        "file_sha256": {name: sha256((used_data / name).read_bytes()) for name in hashes},
        "hdb_rows_in_each_stage": count, "hdb_sample_date_by_stage": date_formats,
        "hdb_NIL_sale_rows_by_stage": dict(nil_rows),
        "hdb_distinct_addresses_with_NIL_by_stage": {name: len(values) for name, values in nil_addresses.items()},
        "hdb_changes": dict(changes),
        "hdb_addresses_with_leading_postal_zero_lost": len(zero_stripped_addresses),
        "team_sales_and_bundle_bytes_equal": (used_data / SALES).read_bytes() == (IMPORT / SALES).read_bytes(),
        "team_rail_and_bundle_bytes_equal": (used_data / RAIL).read_bytes() == rail_file,
        "team_place_rows": len(team_place_rows),
        "team_places_is_literal_prefix_of_bundled_places": places_file.startswith(team_places),
        "team_places_is_parsed_prefix_of_bundled_places": team_place_rows == bundled_place_rows[:len(team_place_rows)],
    }
    if rail_intermediate:
        content = rail_intermediate.read_bytes()
        header, before = csv_records(content)
        final_header, after = csv_records(rail_file)
        result["rail_intermediate"] = {
            **file_details(content, header, before),
            "bundled_columns_added": [key for key in final_header if key not in header],
            "bundled_text_differences": {
                key or "(unnamed index)": sum(a[key] != b[key] for a, b in zip(before, after, strict=True))
                for key in header
            },
            "intermediate_to_bundled_postals_recoverable_by_padding": sum(
                a["POSTAL"] == b["POSTAL"].zfill(6) for a, b in zip(before, after, strict=True)
            ),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-archive", type=Path, required=True)
    parser.add_argument("--cleaned-archive", type=Path, required=True)
    parser.add_argument("--dataset-b", type=Path, required=True)
    parser.add_argument("--dataset-c-legacy", type=Path, required=True)
    parser.add_argument("--dataset-c-dated", type=Path, required=True)
    parser.add_argument("--used-data", type=Path, required=True, help="directory with the team's final and intermediate exports")
    parser.add_argument("--rail-intermediate", type=Path, help="optional team unused_raw_data railway CSV")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    places_file = (IMPORT / PLACES).read_bytes()
    _, place_rows = csv_records(places_file)
    places = by_key(place_rows, "block_id")
    with ZipFile(args.raw_archive) as raw, ZipFile(args.cleaned_archive) as cleaned:
        rail = rail_audit({
            "kaggle_b_v1_TrainStationLocation.csv": args.dataset_b.read_bytes(),
            "kaggle_c_v3_mrt_lrt_stations.csv": args.dataset_c_legacy.read_bytes(),
            "kaggle_c_v3_mrt_lrt_stations_2025-01-14.csv": args.dataset_c_dated.read_bytes(),
            "team_raw_mrt_lrt_full_list.csv": raw.read(RAIL),
            "team_raw_mrt_station_locations.csv": raw.read("mrt_station_locations.csv"),
            "team_cleaned_mrt_stations_cleaned.csv": cleaned.read("cleaned_v2/mrt_stations_cleaned.csv"),
            "tracked_mrt_stations_sample.csv": (ROOT / "data" / "samples" / "mrt_stations_sample.csv").read_bytes(),
            "bundled_mrt_lrt_full_list.csv": (IMPORT / RAIL).read_bytes(),
        }, places)
        hdb = hdb_audit(raw, cleaned, places)
    result = {
        "rail": rail, "hdb": hdb,
        "team_exports": team_export_audit(args.used_data, args.rail_intermediate, places_file, (IMPORT / RAIL).read_bytes()),
        "places": {"rows": len(places), "sha256": sha256(places_file),
                   "ids_are_consecutive_in_file_order": list(map(int, places)) == list(range(1, len(places) + 1))},
    }
    output = json.dumps(result, indent=2, default=str) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
