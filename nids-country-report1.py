import requests
import pycountry
import math


CAIDA_URL = "https://api.asrank.caida.org/v2/graphql"

TOP_N = 15
PAGE_SIZE = 5000


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
# GraphQL query
# --------------------------------

query = """
query GetASNs($first: Int!, $offset: Int!) {
    asns(
        first: $first
        offset: $offset
        sort: "rank"
    ) {
        totalCount

        pageInfo {
            first
            offset
            hasNextPage
        }

        edges {
            node {
                asn
                asnName
                rank

                country {
                    iso
                }

                cone {
                    numberAsns
                }
            }
        }
    }
}
"""


# --------------------------------
# Find top ASNs for country
# --------------------------------

country_asns = []
seen_asns = set()

offset = 0
page_number = 1
total_pages = None


while len(country_asns) < TOP_N:

    variables = {
        "first": PAGE_SIZE,
        "offset": offset
    }

    try:
        response = requests.post(
            CAIDA_URL,
            json={
                "query": query,
                "variables": variables
            },
            timeout=30
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print("Error fetching CAIDA data:")
        print(e)
        break


    caida_data = response.json()


    # --------------------------------
    # Check for GraphQL errors
    # --------------------------------

    if "errors" in caida_data:
        print("CAIDA GraphQL error:")

        for error in caida_data["errors"]:
            print(error["message"])

        break


    asns = caida_data["data"]["asns"]

    total_count = asns["totalCount"]
    edges = asns["edges"]
    page_info = asns["pageInfo"]


    # --------------------------------
    # Calculate total pages
    # --------------------------------

    if total_pages is None:
        total_pages = math.ceil(
            total_count / PAGE_SIZE
        )


    # No more results

    if not edges:
        break


    # --------------------------------
    # Debug pagination
    # --------------------------------

    first_rank = edges[0]["node"]["rank"]
    last_rank = edges[-1]["node"]["rank"]

    print(
        f"DEBUG: page = {page_number} "
        f"results = {len(edges)} "
        f"first rank = {first_rank} "
        f"last rank = {last_rank}"
    )


    # --------------------------------
    # Search this page
    # --------------------------------

    for edge in edges:

        item = edge["node"]

        country = (
            item.get("country") or {}
        ).get(
            "iso",
            "Unknown"
        )


        # Skip ASNs from other countries

        if country != country_code:
            continue


        asn = item["asn"]


        # Skip duplicates

        if asn in seen_asns:
            continue


        country_asns.append(item)
        seen_asns.add(asn)


        # Stop once we have top 15

        if len(country_asns) >= TOP_N:
            break


    print(
        f"Checked page {page_number}/{total_pages} "
        f"- found {len(country_asns)}/{TOP_N}"
    )


    # --------------------------------
    # Stop if top 15 found
    # --------------------------------

    if len(country_asns) >= TOP_N:
        break


    # --------------------------------
    # Stop if API has no more pages
    # --------------------------------

    if not page_info["hasNextPage"]:
        break


    # --------------------------------
    # Move forward 5000 ASNs
    # --------------------------------

    offset += PAGE_SIZE
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


# --------------------------------
# Fewer than 15 exist
# --------------------------------

if len(country_asns) < TOP_N:

    print()

    print(
        f"Only {len(country_asns)} ranked ASNs were found "
        f"for {country_name}."
    )