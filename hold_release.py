import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
import uuid

import httpx
import tomli

with open("myConfig.toml", "rb") as file:
    config = tomli.load(file)

# Setup account details
# The keys should be stored in the myConfig.toml file,
# stored in the same location as this script.
ACCESS_KEY: str = config.get("access_key")
SECRET_KEY: str = config.get("secret_key")
APP_ID: str = config.get("app_id")
APP_KEY: str = config.get("app_key")

# Generate UUID based on RFC4122 and Date/Time based on RFC1123
request_id: str = str(uuid.uuid4())
hdr_date: str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %Z")
end_time: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
time_delta: datetime = datetime.now(timezone.utc) + timedelta(hours=1)
start_time: str = time_delta.strftime("%Y-%m-%dT%H:%M:%S%z")

# Endpoint information
BASE_URL: str = config.get("base_url")
FIND_HELD_MESSAGES: str = "/api/gateway/get-hold-message-list"
RELEASE_MESSAGE: str = "/api/gateway/hold-release"


def auth(uri: str) -> str:
    """
    Generates Authorization Signature - see
    https://www.mimecast.com/tech-connect/documentation/api-overview/authorization/

    Args:
        uri (String): The endpoint URI
    Returns:
        Authorization signature as a string
    """
    # Generate Authorization
    data_to_sign = f"{hdr_date}:{request_id}:{uri}:{APP_KEY}"
    hmac_sha1 = hmac.new(
        base64.b64decode(SECRET_KEY),
        data_to_sign.encode("utf-8"),
        digestmod=hashlib.sha1,
    ).digest()
    sig = base64.b64encode(hmac_sha1).rstrip()

    return f"MC {ACCESS_KEY}:{str(sig.decode())}"


def send_request(uri: str, body: any) -> httpx.Response:
    """
    Sends a POST request to a selected Mimecast endpoint

    Args:
        uri (String): The endpoint URI
        body (Dict): A dictionary of the fields required - see the endpoint
        documentation for the specific endpoint.
    Returns:
        JSON response from the provided endpoint as a dict
    """

    response = httpx.post(
        url=BASE_URL + uri,
        headers={
            "Authorization": auth(uri),
            "x-mc-app-id": APP_ID,
            "x-mc-date": hdr_date,
            "x-mc-req-id": request_id,
            "Content-Type": "application/json",
        },
        data=body,
        timeout=5
    )
    return response.json()


# Get a list of held messages
payload = json.dumps({
    "meta": {
        "pagination": {
            "pageSize": 500
        }
    },
    "data": [
        {
            "admin": True,
            "start": start_time,
            "searchBy": {
                "fieldName": "reasonCode",
                "value": "default_inbound_attachment_protect_definition"
            },
            "end": end_time
        }
    ]
})

get_held_messages = send_request(FIND_HELD_MESSAGES, payload)
messages_to_release = [
    message_id["id"] for message_id in get_held_messages["data"]
]

# Release messages
for message_id in messages_to_release:
    payload = json.dumps({
        "data": [
            {
                "id": message_id
            }
        ]
    })

    send_request(RELEASE_MESSAGE, payload)
