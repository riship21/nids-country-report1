import requests
import pycountry
import math


CAIDA_URL = "https://api.asrank.caida.org/v2/graphql"

TOP_N = 15
PAGE_SIZE = 5000


# --------------------------------
# GraphQL query
# --------------------------------

QUERY = """
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


# ================================================================
# GET TOP ASNs FOR COUNTRY
# ================================================================

def get_top_country_asns(
    country_input,
    top_n=TOP_N,
    page_size=PAGE_SIZE
):

    # --------------------------------
    # Convert country name/code
    # --------------------------------

    try:

        country_obj = pycountry.countries.lookup(
            country_input
        )

        country_code = country_obj.alpha_2
        country_name = country_obj.name

    except LookupError:

        raise ValueError(
            f"Country not found: {country_input}"
        )


    # --------------------------------
    # Variables
    # --------------------------------

    top_country_asns = []

    seen_asns = set()

    total_country_asns = 0

    offset = 0
    page_number = 1

    total_count = None
    total_pages = None

    records_checked = 0


    print()
    print(
        f"Scanning CAIDA ASRank for "
        f"{country_name} ({country_code})..."
    )

    print()


    # ============================================================
    # SCAN ENTIRE CAIDA DATASET
    # ============================================================

    while True:

        variables = {
            "first": page_size,
            "offset": offset
        }


        try:

            response = requests.post(
                CAIDA_URL,
                json={
                    "query": QUERY,
                    "variables": variables
                },
                timeout=30
            )

            response.raise_for_status()

        except requests.RequestException as e:

            raise RuntimeError(
                f"Error fetching CAIDA data: {e}"
            )


        caida_data = response.json()


        # --------------------------------
        # Check GraphQL errors
        # --------------------------------

        if "errors" in caida_data:

            messages = []

            for error in caida_data["errors"]:

                messages.append(
                    error.get(
                        "message",
                        "Unknown GraphQL error"
                    )
                )

            raise RuntimeError(
                "\n".join(messages)
            )


        asns = caida_data["data"]["asns"]

        total_count = asns["totalCount"]

        edges = asns["edges"]

        page_info = asns["pageInfo"]


        # --------------------------------
        # No more records
        # --------------------------------

        if not edges:

            break


        # --------------------------------
        # Calculate pages once
        # --------------------------------

        if total_pages is None:

            total_pages = math.ceil(
                total_count / len(edges)
            )


        # ========================================================
        # SEARCH PAGE
        # ========================================================

        for edge in edges:

            item = edge["node"]


            country = (
                item.get("country") or {}
            ).get(
                "iso",
                "Unknown"
            )


            # Not selected country
            if country != country_code:

                continue


            asn = item["asn"]


            # Skip duplicates
            if asn in seen_asns:

                continue


            seen_asns.add(asn)

            total_country_asns += 1


            # --------------------------------
            # Keep only top N
            #
            # CAIDA already returns records
            # sorted by global ASRank
            # --------------------------------

            if (
                item.get("rank") is not None
                and
                len(top_country_asns) < top_n
            ):

                top_country_asns.append(
                    item
                )


        # --------------------------------
        # Update progress
        # --------------------------------

        records_checked += len(edges)


        progress = (
            records_checked / total_count
        ) * 100


        print(
            f"Page {page_number}/{total_pages} | "
            f"{records_checked:,}/{total_count:,} "
            f"ASNs checked "
            f"({progress:.1f}%) | "
            f"{country_code} matches: "
            f"{total_country_asns}"
        )


        # --------------------------------
        # End of CAIDA dataset
        # --------------------------------

        if not page_info["hasNextPage"]:

            break


        # --------------------------------
        # Move exactly by number returned
        # --------------------------------

        offset += len(edges)

        page_number += 1


    # ============================================================
    # SUMMARY
    # ============================================================

    print()

    print("-" * 100)

    print("CAIDA ASRank scan complete.")

    print(
        f"Dataset coverage: "
        f"{records_checked:,}/"
        f"{total_count:,} ASNs checked "
        f"({records_checked / total_count * 100:.1f}%)"
    )

    print(
        f"Total CAIDA ASNs found for "
        f"{country_name}: "
        f"{total_country_asns}"
    )


    return {
        "country_name": country_name,
        "country_code": country_code,

        "top_asns": top_country_asns,

        "total_country_asns":
            total_country_asns,

        "dataset_total":
            total_count,

        "records_checked":
            records_checked
    }


# ================================================================
# ALLOW THIS FILE TO BE TESTED BY ITSELF
# ================================================================

if __name__ == "__main__":

    country_input = input(
        "Enter a country name or country code: "
    ).strip()


    try:

        result = get_top_country_asns(
            country_input
        )

    except Exception as e:

        print(e)

        exit()


    print()
    print(
        f"Top {len(result['top_asns'])} ASNs for "
        f"{result['country_name']} "
        f"({result['country_code']})"
    )

    print("-" * 100)


    for item in result["top_asns"]:

        asn = item["asn"]

        name = item.get(
            "asnName",
            "Unknown"
        )

        rank = item.get(
            "rank",
            "Unknown"
        )

        cone = (
            item.get("cone") or {}
        ).get(
            "numberAsns",
            0
        )


        print(
            f"AS{asn:<10} "
            f"{name:<40} "
            f"ASRank: {rank:<8} "
            f"Cone: {cone}"
        )