# Changelog

## 0.2.1 — 2026-10-20

### Patch Changes
- Require Python 3.10 or newer, matching what the generated code already needed. `turnkey-http` now requires `turnkey-sdk-types>=0.2.0` and `turnkey-api-key-stamper>=0.1.0`, so a resolver cannot pair it with the 0.1.0 types that lack the activity error classes.

## 0.2.0 — 2026-10-19

### Minor Changes
- Added an error for activities that need authenticator approval.
  - `TurnkeyActivityAuthenticatorsNeededError` is the exception raised when an activity is waiting on authenticator approval.
  - `ACTIVITY_AUTHENTICATORS_NEEDED` is the `TurnkeyErrorCodes` value set on that exception
- Regenerate the SDK from the current public API schema. Main additions: send transaction V2 (eth_send_transaction and sol_send_transaction now use the V2 intents), swaps, earn, secrets, and transaction history. The default polling budget is now 10 retries at 1 second (was 3), and send_signed_request flattens versioned result keys such as ethSendTransactionResultV2.

Breaking changes:
- EthSendTransactionBody uses the V2 intent: `to`, `value`, and `data` are gone; `calls: List[v1EthCallParams]` is required.
- SolSendTransactionBody uses the V2 intent: `signWith` is gone; `signWiths: List[str]` is required.
- CreateOauthProvidersBody.oauthProviders is `List[v1OauthProviderParamsV2]`, and the method sends V2.
- Oauth2AuthenticateBody.nonce is required.
- v1User.mfaPolicies is a required response field.
- v1FiatOnRampBlockchainNetwork no longer has FIAT_ON_RAMP_BLOCKCHAIN_NETWORK_BITCOIN.
- v1CreateTvcDeploymentIntent drops pivotBindAddresses and requires healthCheckType, healthCheckPort, and publicIngressPort.

### Patch Changes
- Typed activity methods now raise `TurnkeyActivityError` or `TurnkeyActivityConsensusNeededError` when an activity does not complete, instead of a pydantic validation error. The errors carry the activity id, status, type, and failure message. `send_signed_request` now unpacks versioned result keys such as `createSubOrganizationResultV7` correctly.

## 0.1.0 — 2026-03-09

### Minor Changes
- Initial release

