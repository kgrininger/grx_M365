import requests


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def get_me(access_token):
    response = requests.get(
        f"{GRAPH_BASE_URL}/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=20,
    )

    if response.status_code >= 400:
        raise Exception(f"Microsoft Graph /me failed: {response.status_code} {response.text}")

    return response.json()