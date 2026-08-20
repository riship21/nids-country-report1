import requests


CAIDA_URL = "https://api.asrank.caida.org/v2/graphql"

PAGE_SIZE = 5000

TEST_RANK = 79006
TEST_COUNTRY = "DE"


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
# Start pagination
# --------------------------------

offset = 0
page_number = 1

found_asns = []
highest_rank_seen = 0


while True:

    variables = {
        "first": PAGE_SIZE,
        "offset": offset
    }


    # --------------------------------
    # Request CAIDA data
    # --------------------------------

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
    # Check GraphQL errors
    # --------------------------------

    if "errors" in caida_data:

        print("CAIDA GraphQL error:")

        for error in caida_data["errors"]:
            print(error.get("message"))

        break


    data = caida_data["data"]["asns"]

    edges = data["edges"]
    page_info = data["pageInfo"]


    # --------------------------------
    # Stop if no results
    # --------------------------------

    if not edges:
        break


    # --------------------------------
    # Get ranks on this page
    # --------------------------------

    ranks = [
        edge["node"]["rank"]
        for edge in edges
        if edge["node"]["rank"] is not None
    ]


    if ranks:

        first_rank = min(ranks)
        last_rank = max(ranks)

        highest_rank_seen = max(
            highest_rank_seen,
            last_rank
        )


        print(
            f"Page {page_number}: "
            f"ranks {first_rank} - {last_rank}"
        )


    # --------------------------------
    # Search for Germany at rank 79006
    # --------------------------------

    for edge in edges:

        item = edge["node"]


        country = (
            item.get("country") or {}
        ).get(
            "iso",
            "Unknown"
        )


        rank = item.get("rank")


        if (
            rank == TEST_RANK
            and country == TEST_COUNTRY
        ):

            found_asns.append(item)


    # --------------------------------
    # Stop if we've passed target rank
    # --------------------------------

    if ranks and min(ranks) > TEST_RANK:
        break


    # --------------------------------
    # Stop if no more pages
    # --------------------------------

    if not page_info["hasNextPage"]:
        break


    # --------------------------------
    # Move to next 5000 ASNs
    # --------------------------------

    offset += PAGE_SIZE
    page_number += 1


# --------------------------------
# Print final results
# --------------------------------

print()
print("-" * 80)

print(
    f"Highest rank reached: "
    f"{highest_rank_seen}"
)

print()


if found_asns:

    print(
        f"Found {len(found_asns)} German ASN(s) "
        f"at global ASRank {TEST_RANK}:"
    )

    print("-" * 80)


    for item in found_asns:

        asn = item["asn"]

        asn_name = item.get(
            "asnName",
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
            f"DE    "
            f"Global ASRank: {rank:<8} "
            f"Cone: {cone_size}"
        )


else:

    print(
        f"No German ASN was found "
        f"at global ASRank {TEST_RANK}."
    )