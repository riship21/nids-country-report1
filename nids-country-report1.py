import requests
import pycountry


CAIDA_URL = "https://api.asrank.caida.org/v2/restful/asns"

TOP_N = 15
PAGE_SIZE = 500


# --------------------------------
# Get country from user
# --------------------------------

country_input = input(
    "Enter a country name or country code: "
).strip()

try:

    country_obj = pycountry.countries.lookup(country_input)

    country_code = country_obj.alpha_2
    country_name = country_obj.name

except LookupError:

    print("Country not found.")
    exit()


# --------------------------------
# Find top 15 ASNs for country
# --------------------------------

country_asns = []

page_number = 1


while len(country_asns) < TOP_N:

    params = {
        "verbose": "",
        "page_size": PAGE_SIZE,
        "page_number": page_number,
        "sort": "rank"
    }


    response = requests.get(
        CAIDA_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    caida_data = response.json()


    asns = caida_data["data"]["asns"]

    edges = asns["edges"]


    # No more results
    if not edges:
        break


    # --------------------------------
    # Check each ASN's country
    # --------------------------------

    for edge in edges:

        item = edge["node"]

        country = (
            item.get("country") or {}
        ).get(
            "iso",
            "Unknown"
        )


        # Only keep selected country
        if country == country_code:

            country_asns.append(item)


        # Stop immediately once we have 15
        if len(country_asns) == TOP_N:
            break


    print(
        f"Checked page {page_number} "
        f"- found {len(country_asns)}/{TOP_N}"
    )

    page_number += 1


# --------------------------------
# Print results
# --------------------------------

print()

print(
    f"Top {len(country_asns)} ASNs for "
    f"{country_name} ({country_code})"
)

print("-" * 100)


for item in country_asns:

    asn = item["asn"]

    asn_name = item.get(
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
        "Unknown"
    )

    cone = item.get("cone") or {}

    cone_size = cone.get(
        "numberAsns",
        0
    )


    print(
        f"AS{asn:<10} "
        f"{asn_name:<35} "
        f"{country:<5} "
        f"Global ASRank: {rank:<8} "
        f"Cone: {cone_size}"
    )