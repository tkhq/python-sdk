import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from base64 import urlsafe_b64encode
import requests

ENDPOINT = "https://api.turnkey.com/public/v1/whoami"
API_PUB_KEY = "<your API key>"
API_PRIV_KEY = "<your API key>"
ORG_ID = "<your org ID>"

# Create payload
payload = {
    "organizationId": ORG_ID
}
payload_str = json.dumps(payload)

# Derive private key 
private_key = ec.derive_private_key(int(API_PRIV_KEY, 16), ec.SECP256R1())

# Sign payload
signature = private_key.sign(payload_str.encode(), ec.ECDSA(hashes.SHA256()))

# Create stamp
stamp = {
    "publicKey": API_PUB_KEY,
    "scheme": "SIGNATURE_SCHEME_TK_API_P256",
    "signature": signature.hex(),
}
encoded_stamp = urlsafe_b64encode(json.dumps(stamp).encode()).decode().rstrip("=")

headers = {
    'Content-Type': 'application/json',
    'X-Stamp': encoded_stamp,
}

# Make post request to turnkey API 
resp = requests.post(ENDPOINT, headers=headers, data=payload_str)
print(resp.status_code, resp.text)