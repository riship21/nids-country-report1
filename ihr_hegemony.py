import requests


IHR_URL = "https://www.ihr.live/ihr/api/hegemony"


# ================================================================
# CREATE RANKS
#
# Highest Hegemony = Rank 1
# ================================================================

def create_rank_map(scores):

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
        # Equal scores get equal ranks
        # --------------------------------

        if (
            previous_score is None
            or
            score != previous_score
        ):

            current_rank = position


        ranks[asn] = current_rank

        previous_score = score


    return ranks


# ================================================================
# GET CURRENT GLOBAL HEGEMONY SNAPSHOT
# ================================================================

def get_global_hegemony(af=4):

    print()
    print(
        "Fetching current IHR "
        "Global Hegemony data..."
    )


    try:

        response = requests.get(
            IHR_URL,
            params={
                "originasn": 0,
                "af": af,
                "page": 1
            },
            timeout=60
        )

        response.raise_for_status()

    except requests.RequestException as e:

        raise RuntimeError(
            f"Error fetching IHR data: {e}"
        )


    data = response.json()


    results = data.get(
        "results",
        []
    )


    if not results:

        raise RuntimeError(
            "IHR returned no Hegemony data."
        )


    # ============================================================
    # VALID GLOBAL ROWS
    # ============================================================

    valid_rows = []


    for row in results:

        asn = row.get("asn")
        hege = row.get("hege")
        timebin = row.get("timebin")


        if (
            row.get("originasn") == 0
            and
            row.get("af") == af
            and
            asn is not None
            and
            asn > 0
            and
            hege is not None
            and
            timebin is not None
        ):

            valid_rows.append(
                row
            )


    if not valid_rows:

        raise RuntimeError(
            "No valid global IPv4 "
            "Hegemony rows found."
        )


    # ============================================================
    # FIND NEWEST SNAPSHOT
    # ============================================================

    latest_timebin = max(
        row["timebin"]
        for row in valid_rows
    )


    # ============================================================
    # KEEP ONLY LATEST SNAPSHOT
    # ============================================================

    latest_rows = []


    for row in valid_rows:

        if (
            row["timebin"]
            == latest_timebin
        ):

            latest_rows.append(
                row
            )


    # ============================================================
    # ASN -> HEGEMONY
    # ============================================================

    scores = {}


    for row in latest_rows:

        asn = int(
            row["asn"]
        )

        hege = float(
            row["hege"]
        )


        # --------------------------------
        # Normally only one exists,
        # but this protects against
        # accidental duplicates.
        # --------------------------------

        if (
            asn not in scores
            or
            hege > scores[asn]
        ):

            scores[asn] = hege


    # ============================================================
    # GLOBAL RANKS
    # ============================================================

    global_ranks = create_rank_map(
        scores
    )


    print(
        f"IHR snapshot: "
        f"{latest_timebin}"
    )

    print(
        f"Global IPv{af} ASNs ranked: "
        f"{len(scores):,}"
    )


    return {
        "snapshot": latest_timebin,
        "scores": scores,
        "global_ranks":
            global_ranks
    }


# ================================================================
# ADD HEGEMONY TO CAIDA ASNs
# ================================================================

def rank_country_asns(
    country_asns,
    af=4
):

    # --------------------------------
    # Download global snapshot once
    # --------------------------------

    global_data = get_global_hegemony(
        af
    )


    global_scores = (
        global_data["scores"]
    )

    global_ranks = (
        global_data["global_ranks"]
    )


    # ============================================================
    # GET HEGEMONY FOR SELECTED CAIDA ASNs
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
    # COUNTRY RANK
    #
    # IMPORTANT:
    # This ranks ONLY the ASNs selected
    # by our CAIDA top-15 step.
    # ============================================================

    country_ranks = create_rank_map(
        selected_scores
    )


    # ============================================================
    # CREATE FINAL ROWS
    # ============================================================

    report_rows = []


    for item in country_asns:

        asn = int(
            item["asn"]
        )


        hege = global_scores.get(
            asn
        )


        country_rank = (
            country_ranks.get(
                asn
            )
        )


        global_rank = (
            global_ranks.get(
                asn
            )
        )


        report_rows.append(
            {
                "asn": asn,

                "asn_name":
                    item.get(
                        "asnName",
                        "Unknown"
                    ),

                "country":
                    (
                        item.get(
                            "country"
                        )
                        or {}
                    ).get(
                        "iso",
                        "Unknown"
                    ),

                "caida_rank":
                    item.get(
                        "rank"
                    ),

                "cone":
                    (
                        item.get(
                            "cone"
                        )
                        or {}
                    ).get(
                        "numberAsns",
                        0
                    ),

                "hegemony":
                    hege,

                "country_hegemony_rank":
                    country_rank,

                "global_hegemony_rank":
                    global_rank
            }
        )


    # ============================================================
    # SORT FINAL TABLE BY COUNTRY HEGEMONY
    # ============================================================

    report_rows.sort(
        key=lambda row: (
            row[
                "country_hegemony_rank"
            ]
            is None,

            row[
                "country_hegemony_rank"
            ]
            if row[
                "country_hegemony_rank"
            ]
            is not None
            else float("inf")
        )
    )


    return {
        "snapshot":
            global_data["snapshot"],

        "rows":
            report_rows
    }