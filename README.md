# python-sdk
This repository contains support for calling the Turnkey API using Python

## Stamper 

The stamper service stamps requests to the Turnkey API and authenticates the requests. In order to use the stamper to successfully make API calls you need to have a Turnkey organization and an API key associated with the organization that is authorized to make the call that you are trying to make. 

Fill out the fields at the beginning of the python stamper script with the correct information.

```
ENDPOINT = "https://api.turnkey.com/public/v1/whoami"
API_PUB_KEY = "<your API key>"
API_PRIV_KEY = "<your API key>"
ORG_ID = "<your org ID>"
```