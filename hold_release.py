import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
import uuid

import httpx
import tomli

with open("config.toml", "rb") as file:
    config = tomli.load(file)

# Setup account details
# The keys should be stored in the config.toml file,
# stored in the same location as this script.
ACCESS_KEY: str = config.get("access_key")
SECRET_KEY: str = config.get("secret_key")
APP_ID: str = config.get("app_id")
APP_KEY: str = config.get("app_key")

# Generate UUID based on RFC4122 and Date/Time based on RFC1123
request_id: str = str(uuid.uuid4())
hdr_date: str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %Z")
end_time: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
time_delta: datetime = datetime.now(timezone.utc) - timedelta(hours=1)
start_time: str = time_delta.strftime("%Y-%m-%dT%H:%M:%S%z")

# Endpoint information
BASE_URL: str = config.get("base_url")
GET_ATTACHMENT_LOGS: str = "/api/ttp/attachment/get-logs"
FIND_MESSAGE_ID: str = "/api/message-finder/search"
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


# Get a list of failed messages
payload = json.dumps({
    "meta": {
        "pagination": {
            "pageSize": 500
        }
    },
    "data": [
        {
            "oldestFirst": False,
            "from": start_time,
            "route": "all",
            "to": end_time,
            "scanResult": "error"
        }
    ]
})

get_held_messages = send_request(GET_ATTACHMENT_LOGS, payload)
message_ids_to_find: list[str] = [
    msg_id['messageId'] for msg_id in
    get_held_messages['data'][0]['attachmentLogs']
]

# Deduplicate message_ids_to_find
message_ids_set: set[str] = set(message_ids_to_find)

# Get IDs of failed messages
messages_to_release = []
for msg_id in message_ids_set:
    payload = json.dumps({
        "data": [
            {
                "messageId": msg_id
            }
        ]
    })

    find_message_ids = send_request(FIND_MESSAGE_ID, payload)
    messages_to_release.append(find_message_ids['data'][0]['trackedEmails'][0]['id'])

# Release Messages
for message_id in messages_to_release:
    payload = json.dumps({
        "data": [
            {
                "id": message_id
            }
        ]
    })

    send_request(RELEASE_MESSAGE, payload)
