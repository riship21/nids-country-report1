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
# Scan CAIDA dataset
# --------------------------------

top_country_asns = []

seen_country_asns = set()

total_country_asns = 0
ranked_country_asns = 0

offset = 0
page_number = 1

total_count = None
total_pages = None
effective_page_size = None

records_checked = 0

scan_complete = False


print()
print(
    f"Scanning CAIDA ASRank for "
    f"{country_name} ({country_code})..."
)
print()


while True:

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

        print()
        print("Error fetching CAIDA data:")
        print(e)

        break


    caida_data = response.json()


    # --------------------------------
    # Check GraphQL errors
    # --------------------------------

    if "errors" in caida_data:

        print()
        print("CAIDA GraphQL error:")

        for error in caida_data["errors"]:
            print(error["message"])

        break


    asns = caida_data["data"]["asns"]

    total_count = asns["totalCount"]
    edges = asns["edges"]
    page_info = asns["pageInfo"]


    # --------------------------------
    # No results returned
    # --------------------------------

    if not edges:
        break


    # --------------------------------
    # Determine actual page size
    # --------------------------------

    if effective_page_size is None:

        effective_page_size = len(edges)

        total_pages = math.ceil(
            total_count / effective_page_size
        )


    # --------------------------------
    # Search current page
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


        # Skip duplicate ASN records
        if asn in seen_country_asns:
            continue


        seen_country_asns.add(asn)

        total_country_asns += 1


        # --------------------------------
        # Count only ranked ASNs
        # --------------------------------

        rank = item.get("rank")

        if rank is None:
            continue


        ranked_country_asns += 1


        # --------------------------------
        # Keep only the top 15
        # --------------------------------

        if len(top_country_asns) < TOP_N:
            top_country_asns.append(item)


    # --------------------------------
    # Update number of records scanned
    # --------------------------------

    records_checked += len(edges)

    progress = (
        records_checked / total_count
    ) * 100


    # --------------------------------
    # Progress output
    # --------------------------------

    print(
        f"Page {page_number}/{total_pages} | "
        f"{records_checked:,}/{total_count:,} ASNs checked "
        f"({progress:.1f}%) | "
        f"{country_code} matches: {total_country_asns}"
    )


    # --------------------------------
    # Reached end of CAIDA dataset
    # --------------------------------

    if not page_info["hasNextPage"]:

        scan_complete = True
        break


    # --------------------------------
    # Move to next batch
    #
    # Use number actually returned rather
    # than assuming CAIDA returned 5000.
    # --------------------------------

    offset += len(edges)

    page_number += 1


# --------------------------------
# Scan summary
# --------------------------------

print()
print("-" * 100)

if scan_complete:

    print("CAIDA ASRank scan complete.")

    print(
        f"Dataset coverage: "
        f"{records_checked:,}/{total_count:,} ASNs checked "
        f"(100.0%)"
    )

else:

    print("WARNING: CAIDA ASRank scan did not complete.")

    if total_count is not None:

        print(
            f"Dataset coverage: "
            f"{records_checked:,}/{total_count:,} ASNs checked"
        )


print(
    f"Total CAIDA ASNs found for {country_name}: "
    f"{total_country_asns}"
)

print(
    f"Ranked ASNs found for {country_name}: "
    f"{ranked_country_asns}"
)


# --------------------------------
# Print top ASNs
# --------------------------------

print()
print(
    f"Top {len(top_country_asns)} ranked ASNs for "
    f"{country_name} ({country_code})"
)

print("-" * 100)


for item in top_country_asns:

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
# Fewer than requested number exist
# --------------------------------

if ranked_country_asns < TOP_N:

    print()

    print(
        f"Only {ranked_country_asns} ranked ASNs "
        f"were found for {country_name}."
    )