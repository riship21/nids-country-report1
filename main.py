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
# PART 1 - CAIDA ASRank
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
    caida_result["country_name"]
)

country_code = (
    caida_result["country_code"]
)

country_asns = (
    caida_result["top_asns"]
)


# ================================================================
# SHOW CAIDA TOP ASNs
# ================================================================

print()
print()

print(
    f"Top {len(country_asns)} "
    f"CAIDA ASRank ASNs for "
    f"{country_name} ({country_code})"
)

print("-" * 110)


print(
    f"{'AS':<14}"
    f"{'Org Name':<42}"
    f"{'Country':<10}"
    f"{'ASRank':<12}"
    f"{'Cone':<10}"
)


print("-" * 110)


for item in country_asns:

    asn = item["asn"]

    name = item.get(
        "asnName",
        "Unknown"
    )

    country = (
        item.get("country") or {}
    ).get(
        "iso",
        "Unknown"
    )

    rank = item.get(
        "rank",
        "N/A"
    )

    cone = (
        item.get("cone") or {}
    ).get(
        "numberAsns",
        0
    )


    print(
        f"AS{asn:<12}"
        f"{name:<42}"
        f"{country:<10}"
        f"{str(rank):<12}"
        f"{str(cone):<10}"
    )


# ================================================================
# PART 2 - IHR HEGEMONY
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
    hegemony_result["rows"]
)

snapshot = (
    hegemony_result["snapshot"]
)


# ================================================================
# FINAL REPORT 1
# ================================================================

print()
print()

print("=" * 125)

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

print("=" * 125)

print()


print(
    f"{'AS':<14}"
    f"{'Org Name':<38}"
    f"{'Country':<10}"
    f"{'Hegemony':<16}"
    f"{'Country Rank':<20}"
    f"{'Global Rank':<15}"
)


print("-" * 125)


for row in report_rows:

    # --------------------------------
    # Hegemony
    # --------------------------------

    if row["hegemony"] is None:

        hegemony = "N/A"

    else:

        hegemony = (
            f"{row['hegemony']:.6f}"
        )


    # --------------------------------
    # Country Hegemony rank
    # --------------------------------

    country_rank = (
        row[
            "country_hegemony_rank"
        ]
    )


    if country_rank is None:

        country_rank = "N/A"


    # --------------------------------
    # Global Hegemony rank
    # --------------------------------

    global_rank = (
        row[
            "global_hegemony_rank"
        ]
    )


    if global_rank is None:

        global_rank = "N/A"


    # --------------------------------
    # Print
    # --------------------------------

    print(
        f"AS{row['asn']:<12}"
        f"{row['asn_name']:<38}"
        f"{row['country']:<10}"
        f"{hegemony:<16}"
        f"{str(country_rank):<20}"
        f"{str(global_rank):<15}"
    )


print("-" * 125)


# ================================================================
# SUMMARY
# ================================================================

hegemony_count = sum(
    1
    for row in report_rows
    if row["hegemony"] is not None
)


print()

print(
    f"CAIDA ASNs selected: "
    f"{len(country_asns)}"
)

print(
    f"IHR Hegemony values found: "
    f"{hegemony_count}/"
    f"{len(country_asns)}"
)

print(
    f"Total CAIDA ASNs associated with "
    f"{country_name}: "
    f"{caida_result['total_country_asns']}"
)