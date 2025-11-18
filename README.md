# python-sdk
This repository contains support for interacting with the Turnkey API using Python

Unlike other languages ([Typescript](https://github.com/tkhq/sdk), [Ruby](https://github.com/tkhq/ruby-sdk)), we do not yet offer a full SDK for Python.

If you are working on a project in Python and would benefit from a Python SDK please open an issue or get in touch with us (hello@turnkey.com) and we can discuss prioritizing this.

## Stamper 

The stamper utility stamps requests to the Turnkey API and authenticates the requests. In order to use the stamper to successfully make API calls you need to have a Turnkey organization and an associated API key that is authorized to make requests. 

Fill out the fields at the beginning of the python stamper script with the correct information.

```
ENDPOINT = "https://api.turnkey.com/public/v1/whoami"
API_PUBLIC_KEY="<Turnkey API Public Key (that starts with 02 or 03)>"
API_PRIVATE_KEY="<Turnkey API Private Key>"
ORG_ID = "<your org ID>"
```
