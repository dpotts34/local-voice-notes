# iPhone Shortcut setup

This is a generic recipe, not a device-tested Shortcut export. Audio format support depends on your ASR service; first test a harmless recording in the actual format your phone produces. The service has no application-layer authentication, so use it only on a network you trust. A phone cannot reach the default `127.0.0.1` listener. Before using a Shortcut, bind the service to one private interface address and apply a firewall rule limited to trusted devices, or use a trusted private overlay network. Do not expose the unauthenticated endpoint to the internet.

1. Create a Shortcut that records audio or receives an audio file from the Share Sheet.
2. Generate a fresh UUID for `request_id` for each recording. Use lowercase canonical UUID text with hyphens. Reuse it only when retrying the same retained audio bytes.
3. For a new thread, set `thread_id` to that same UUID. For a follow-up, select an existing thread ID from your own saved list and still generate a new request ID. Reusing a thread ID groups notes; the formatter does not load prior notes as conversational context.
4. Add **Get Contents of URL** and set:
   - URL: `http://<private-service-address>:8791/v1/voice-notes`
   - Method: `POST`
   - Request Body: **Form**
   - `audio`: **File** field set to the recorded audio value
   - `request_id`: **Text** field set to the new UUID
   - `thread_id`: **Text** field set as described above
   - Headers: none. Do not set `Content-Type`; Shortcuts must generate the multipart boundary.
5. Show the response. HTTP `202` with `status: received` confirms durable intake only, not completed transcription.
6. Afterward, query `GET http://<private-service-address>:8791/v1/jobs/<request_id>` for terminal status. The recent thread list is `GET http://<private-service-address>:8791/v1/threads?limit=10`.

If the server replies `multipart form required`, verify the request body is **Form** and `audio` is a **File** field, not text. Do not retry with a new request ID unless you are intentionally submitting a different captured audio value.
