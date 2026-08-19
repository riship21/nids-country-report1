import requests
CAIDA_URL = "https://api.asrank.caida.org/v2/restful/asns"

country_code = "HU"
TOP_N = 15


params = {
    "country": country_code,
    "verbose": "",
    "page_size": TOP_N,
    "page_number": 1,
    "sort": "rank"
}


response = requests.get(
    CAIDA_URL,
    params=params,
    timeout=30
)

response.raise_for_status()

caida_data = response.json()


# --------------------------------
# Get ASRank response
# --------------------------------

asns = caida_data["data"]["asns"]

total = asns["totalCount"]

edges = asns["edges"]


# Sort by CAIDA rank just to make sure
edges = sorted(
    edges,
    key=lambda edge: edge["node"].get(
        "rank",
        float("inf")
    )
)


# Keep ONLY top 15
edges = edges[:TOP_N]


print(f"\nTotal ASNs in {country_code}: {total}")

print(
    f"\nTop {TOP_N} ASNs for {country_code}"
)

print("-" * 90)


for edge in edges:

    item = edge["node"]

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
        f"Rank: {rank:<8} "
        f"Cone: {cone_size}"
    )