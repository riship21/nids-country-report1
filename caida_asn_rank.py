import math
import requests
import pycountry


CAIDA_URL = "https://api.asrank.caida.org/v2/graphql"

TOP_N = 15
PAGE_SIZE = 5000


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
# GET COUNTRY'S TOP CAIDA ASNs
# ================================================================

def get_top_country_asns(
    country_input,
    top_n=TOP_N,
    page_size=PAGE_SIZE
):

    # ------------------------------------------------
    # Convert country input to country name + code
    # ------------------------------------------------

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


    # ------------------------------------------------
    # Variables
    # ------------------------------------------------

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
    # SCAN COMPLETE CAIDA DATASET
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


        # ------------------------------------------------
        # GraphQL errors
        # ------------------------------------------------

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


        asns_data = caida_data["data"]["asns"]

        total_count = asns_data["totalCount"]

        edges = asns_data["edges"]

        page_info = asns_data["pageInfo"]


        # ------------------------------------------------
        # No more results
        # ------------------------------------------------

        if not edges:
            break


        # ------------------------------------------------
        # Calculate total pages
        # ------------------------------------------------

        if total_pages is None:

            actual_page_size = len(edges)

            total_pages = math.ceil(
                total_count / actual_page_size
            )


        # ========================================================
        # SEARCH CURRENT PAGE
        # ========================================================

        for edge in edges:

            item = edge["node"]


            country = (
                item.get("country") or {}
            ).get(
                "iso",
                "Unknown"
            )


            # Not our selected country
            if country != country_code:
                continue


            asn = int(
                item["asn"]
            )


            # Avoid duplicates
            if asn in seen_asns:
                continue


            seen_asns.add(asn)

            total_country_asns += 1


            # ------------------------------------------------
            # Keep only the first top N ranked ASNs
            #
            # CAIDA results are already sorted by rank.
            # ------------------------------------------------

            if (
                item.get("rank") is not None
                and
                len(top_country_asns) < top_n
            ):

                top_country_asns.append(
                    item
                )


        # ------------------------------------------------
        # Progress
        # ------------------------------------------------

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


        # ------------------------------------------------
        # End of dataset
        # ------------------------------------------------

        if not page_info["hasNextPage"]:
            break


        # ------------------------------------------------
        # Move forward by number actually returned
        # ------------------------------------------------

        offset += len(edges)

        page_number += 1


    # ============================================================
    # CAIDA SUMMARY
    # ============================================================

    print()
    print("-" * 100)

    print("CAIDA ASRank scan complete.")

    print(
        f"Dataset coverage: "
        f"{records_checked:,}/{total_count:,} "
        f"ASNs checked "
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
# ALLOW THIS FILE TO BE TESTED SEPARATELY
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
        f"Top {len(result['top_asns'])} "
        f"CAIDA ASRank ASNs for "
        f"{result['country_name']} "
        f"({result['country_code']})"
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


    for item in result["top_asns"]:

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