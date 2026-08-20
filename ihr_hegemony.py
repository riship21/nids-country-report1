import requests

from datetime import (
    datetime,
    timezone,
    timedelta
)


IHR_URL = "https://www.ihr.live/ihr/api/hegemony"


# ================================================================
# CREATE RANKS
#
# Highest Hegemony = Rank 1
# ================================================================

def create_rank_map(scores):

    # scores example:
    #
    # {
    #     3356: 0.20,
    #     174: 0.07,
    #     1299: 0.13
    # }

    sorted_scores = sorted(
        scores.items(),
        key=lambda item: (
            -item[1],
            item[0]
        )
    )


    ranks = {}

    previous_score = None
    current_rank = 0


    for position, (
        asn,
        score
    ) in enumerate(
        sorted_scores,
        start=1
    ):

        # --------------------------------
        # Equal Hegemony values
        # receive the same rank
        # --------------------------------

        if (
            previous_score is None
            or score != previous_score
        ):

            current_rank = position


        ranks[asn] = current_rank

        previous_score = score


    return ranks


# ================================================================
# ROUND CURRENT UTC TIME DOWN TO
# NEAREST 15 MINUTES
# ================================================================

def floor_to_15_minutes(dt):

    minutes_to_remove = (
        dt.minute % 15
    )


    return dt.replace(
        second=0,
        microsecond=0
    ) - timedelta(
        minutes=minutes_to_remove
    )


# ================================================================
# FIND LATEST AVAILABLE IHR SNAPSHOT
# ================================================================

def find_latest_snapshot(
    af=4,
    max_lookback_hours=24
):

    print()
    print(
        "Searching for latest available "
        "IHR Hegemony snapshot..."
    )


    # --------------------------------
    # Current UTC time
    # --------------------------------

    now = datetime.now(
        timezone.utc
    )


    # --------------------------------
    # Start at nearest 15-minute
    # timestamp
    # --------------------------------

    candidate = floor_to_15_minutes(
        now
    )


    # --------------------------------
    # Number of 15-minute timestamps
    # to try
    # --------------------------------

    max_attempts = (
        max_lookback_hours * 4
    )


    for _ in range(max_attempts):

        timebin = candidate.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )


        try:

            response = requests.get(
                IHR_URL,
                params={
                    "originasn": 0,
                    "af": af,
                    "timebin": timebin,
                    "page": 1
                },
                timeout=60
            )


            response.raise_for_status()


        except requests.RequestException as e:

            raise RuntimeError(
                f"Error contacting IHR API: {e}"
            )


        data = response.json()


        results = data.get(
            "results",
            []
        )


        # --------------------------------
        # We found an actual snapshot
        # --------------------------------

        if results:

            print(
                f"Latest available IHR snapshot: "
                f"{timebin}"
            )

            return timebin


        # --------------------------------
        # Move backward 15 minutes
        # --------------------------------

        candidate -= timedelta(
            minutes=15
        )


    raise RuntimeError(
        "Could not find an IHR Hegemony "
        f"snapshot within the last "
        f"{max_lookback_hours} hours."
    )


# ================================================================
# FETCH ALL PAGES FOR ONE EXACT SNAPSHOT
# ================================================================

def fetch_snapshot(
    timebin,
    af=4
):

    all_results = []

    page = 1


    while True:

        try:

            response = requests.get(
                IHR_URL,
                params={
                    "originasn": 0,
                    "af": af,
                    "timebin": timebin,
                    "page": page
                },
                timeout=60
            )


            response.raise_for_status()


        except requests.RequestException as e:

            raise RuntimeError(
                f"Error fetching IHR "
                f"Hegemony snapshot: {e}"
            )


        data = response.json()


        page_results = data.get(
            "results",
            []
        )


        all_results.extend(
            page_results
        )


        # --------------------------------
        # No more pages
        # --------------------------------

        if not data.get("next"):

            break


        page += 1


    return all_results


# ================================================================
# GET CURRENT GLOBAL HEGEMONY
# ================================================================

def get_global_hegemony(
    af=4
):

    # --------------------------------
    # Find the newest real snapshot
    # --------------------------------

    latest_timebin = (
        find_latest_snapshot(
            af=af
        )
    )


    print(
        "Fetching current IHR Global "
        "Hegemony data..."
    )


    # --------------------------------
    # Fetch that exact snapshot
    # --------------------------------

    results = fetch_snapshot(
        latest_timebin,
        af=af
    )


    if not results:

        raise RuntimeError(
            "IHR returned no Hegemony "
            "data for the selected snapshot."
        )


    # ============================================================
    # ASN -> HEGEMONY
    # ============================================================

    global_scores = {}


    for row in results:

        # --------------------------------
        # Must be global graph
        # --------------------------------

        if row.get(
            "originasn"
        ) != 0:

            continue


        # --------------------------------
        # Must be requested AF
        # --------------------------------

        if row.get(
            "af"
        ) != af:

            continue


        try:

            asn = int(
                row.get("asn")
            )

        except (
            TypeError,
            ValueError
        ):

            continue


        # --------------------------------
        # Remove special/sentinel values
        #
        # Example:
        # AS-1
        # --------------------------------

        if asn <= 0:

            continue


        hege = row.get(
            "hege"
        )


        if hege is None:

            continue


        hege = float(
            hege
        )


        # --------------------------------
        # Protect against duplicates
        # --------------------------------

        if (
            asn not in global_scores
            or
            hege > global_scores[asn]
        ):

            global_scores[asn] = hege


    if not global_scores:

        raise RuntimeError(
            "No valid global Hegemony "
            "values were found."
        )


    # ============================================================
    # GLOBAL RANKING
    # ============================================================

    global_ranks = create_rank_map(
        global_scores
    )


    print(
        f"Global IPv{af} ASNs ranked: "
        f"{len(global_scores):,}"
    )


    return {
        "snapshot":
            latest_timebin,

        "scores":
            global_scores,

        "global_ranks":
            global_ranks
    }


# ================================================================
# GET HEGEMONY FOR CAIDA-SELECTED ASNs
# ================================================================

def rank_country_asns(
    country_asns,
    af=4
):

    # ============================================================
    # GET GLOBAL IHR DATA
    # ============================================================

    global_data = (
        get_global_hegemony(
            af=af
        )
    )


    global_scores = (
        global_data["scores"]
    )


    global_ranks = (
        global_data[
            "global_ranks"
        ]
    )


    # ============================================================
    # GET SCORES FOR ONLY OUR
    # CAIDA-SELECTED ASNs
    # ============================================================

    selected_scores = {}


    for item in country_asns:

        asn = int(
            item["asn"]
        )


        if asn in global_scores:

            selected_scores[asn] = (
                global_scores[asn]
            )


    # ============================================================
    # COUNTRY HEGEMONY RANK
    #
    # Rank ONLY the ASNs chosen by CAIDA.
    #
    # Highest Hegemony = Country Rank 1
    # ============================================================

    country_ranks = create_rank_map(
        selected_scores
    )


    # ============================================================
    # BUILD FINAL REPORT ROWS
    # ============================================================

    report_rows = []


    for item in country_asns:

        asn = int(
            item["asn"]
        )


        # --------------------------------
        # Hegemony value
        # --------------------------------

        hegemony = (
            global_scores.get(
                asn
            )
        )


        # --------------------------------
        # Country Hegemony rank
        # --------------------------------

        country_hegemony_rank = (
            country_ranks.get(
                asn
            )
        )


        # --------------------------------
        # Global Hegemony rank
        # --------------------------------

        global_hegemony_rank = (
            global_ranks.get(
                asn
            )
        )


        # --------------------------------
        # CAIDA rank
        # --------------------------------

        caida_rank = item.get(
            "rank"
        )


        # --------------------------------
        # Customer cone
        # --------------------------------

        cone = (
            item.get("cone")
            or {}
        ).get(
            "numberAsns",
            0
        )


        # --------------------------------
        # Country
        # --------------------------------

        country = (
            item.get("country")
            or {}
        ).get(
            "iso",
            "Unknown"
        )


        report_rows.append(
            {
                "asn":
                    asn,

                "asn_name":
                    item.get(
                        "asnName",
                        "Unknown"
                    ),

                "country":
                    country,

                "caida_rank":
                    caida_rank,

                "cone":
                    cone,

                "hegemony":
                    hegemony,

                "country_hegemony_rank":
                    country_hegemony_rank,

                "global_hegemony_rank":
                    global_hegemony_rank
            }
        )


    # ============================================================
    # SORT BY COUNTRY HEGEMONY RANK
    # ============================================================

    report_rows.sort(
        key=lambda row: (
            row[
                "country_hegemony_rank"
            ] is None,

            row[
                "country_hegemony_rank"
            ]
            if row[
                "country_hegemony_rank"
            ] is not None
            else float("inf")
        )
    )


    return {
        "snapshot":
            global_data["snapshot"],

        "rows":
            report_rows
    }


# ================================================================
# IF USER RUNS THIS FILE DIRECTLY
# ================================================================

if __name__ == "__main__":

    print(
        "This file contains the "
        "IHR Hegemony functions."
    )

    print(
        "Run main.py to generate "
        "Report 1."
    )