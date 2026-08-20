import requests


IHR_URL = "https://www.ihr.live/ihr/api/hegemony"

test_asns = [
    3356,
    174,
    1299
]


for asn in test_asns:

    response = requests.get(
        IHR_URL,
        params={
            "asn": asn,
            "page": 1
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    results = data.get(
        "results",
        []
    )


    # --------------------------------
    # Find global IPv4 Hegemony rows
    # --------------------------------

    global_rows = []

    for row in results:

        if (
            row.get("originasn") == 0
            and row.get("af") == 4
        ):
            global_rows.append(row)


    print()
    print(f"ASN: AS{asn}")
    print(
        f"Total API results: "
        f"{len(results):,}"
    )

    print(
        f"Global IPv4 results: "
        f"{len(global_rows):,}"
    )


    # --------------------------------
    # Find newest global measurement
    # --------------------------------

    if global_rows:

        latest = max(
            global_rows,
            key=lambda row: row["timebin"]
        )

        print(
            f"Latest time: "
            f"{latest['timebin']}"
        )

        print(
            f"Global Hegemony: "
            f"{latest['hege']}"
        )

    else:

        print(
            "No global IPv4 Hegemony "
            "data found."
        )