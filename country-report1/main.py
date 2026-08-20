from caida_asn_rank import (
    get_top_country_asns
)

from ihr_hegemony import (
    rank_country_asns
)


# ================================================================
# USER INPUT
# ================================================================

country_input = input(
    "Enter a country name or country code: "
).strip()


# ================================================================
# PART 1
# CAIDA ASRank
# ================================================================

try:

    caida_result = (
        get_top_country_asns(
            country_input
        )
    )

except Exception as e:

    print()
    print(
        "CAIDA section failed:"
    )

    print(e)

    exit()


country_name = (
    caida_result[
        "country_name"
    ]
)

country_code = (
    caida_result[
        "country_code"
    ]
)

country_asns = (
    caida_result[
        "top_asns"
    ]
)


# ================================================================
# MAKE SURE CAIDA FOUND SOMETHING
# ================================================================

if not country_asns:

    print()
    print(
        f"No ranked CAIDA ASNs were found "
        f"for {country_name}."
    )

    exit()


# ================================================================
# PART 2
# IHR Hegemony
# ================================================================

try:

    hegemony_result = (
        rank_country_asns(
            country_asns
        )
    )

except Exception as e:

    print()
    print(
        "IHR Hegemony section failed:"
    )

    print(e)

    exit()


report_rows = (
    hegemony_result[
        "rows"
    ]
)

snapshot = (
    hegemony_result[
        "snapshot"
    ]
)


# ================================================================
# FINAL REPORT 1
# ================================================================

print()
print()

print("=" * 160)

print(
    "REPORT 1 - ASN AND HEGEMONY ANALYSIS"
)

print(
    f"Country: "
    f"{country_name} ({country_code})"
)

print(
    f"IHR IPv4 Hegemony snapshot: "
    f"{snapshot}"
)

print("=" * 160)

print()


# ================================================================
# TABLE HEADER
# ================================================================

print(
    f"{'AS':<14}"
    f"{'Org Name':<36}"
    f"{'Country':<10}"
    f"{'CAIDA Rank':<15}"
    f"{'Cone':<12}"
    f"{'Hegemony':<16}"
    f"{'Country Heg. Rank':<20}"
    f"{'Global Heg. Rank':<18}"
)

print("-" * 160)


# ================================================================
# TABLE ROWS
# ================================================================

for row in report_rows:

    # ------------------------------------------------
    # CAIDA Rank
    # ------------------------------------------------

    caida_rank = (
        row["caida_rank"]
    )

    if caida_rank is None:

        caida_rank = "N/A"


    # ------------------------------------------------
    # Customer Cone
    # ------------------------------------------------

    cone = row["cone"]

    if cone is None:

        cone = "N/A"


    # ------------------------------------------------
    # Hegemony
    # ------------------------------------------------

    if row["hegemony"] is None:

        hegemony = "N/A"

    else:

        hegemony = (
            f"{row['hegemony']:.6f}"
        )


    # ------------------------------------------------
    # Country Hegemony Rank
    # ------------------------------------------------

    country_rank = (
        row[
            "country_hegemony_rank"
        ]
    )

    if country_rank is None:

        country_rank = "N/A"


    # ------------------------------------------------
    # Global Hegemony Rank
    # ------------------------------------------------

    global_rank = (
        row[
            "global_hegemony_rank"
        ]
    )

    if global_rank is None:

        global_rank = "N/A"


    # ------------------------------------------------
    # Print row
    # ------------------------------------------------

    print(
        f"AS{row['asn']:<12}"
        f"{row['asn_name']:<36}"
        f"{row['country']:<10}"
        f"{str(caida_rank):<15}"
        f"{str(cone):<12}"
        f"{hegemony:<16}"
        f"{str(country_rank):<20}"
        f"{str(global_rank):<18}"
    )


print("-" * 160)


# ================================================================
# REPORT SUMMARY
# ================================================================

hegemony_count = sum(
    1
    for row in report_rows
    if row["hegemony"] is not None
)


print()

print(
    f"Total CAIDA ASNs associated with "
    f"{country_name}: "
    f"{caida_result['total_country_asns']}"
)

print(
    f"Top CAIDA ASNs selected for analysis: "
    f"{len(country_asns)}"
)

print(
    f"IHR Hegemony values found: "
    f"{hegemony_count}/"
    f"{len(country_asns)}"
)

print()