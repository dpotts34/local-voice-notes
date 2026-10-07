# iPhone Shortcut setup

Instructions only. No tested Shortcut export. First upload a harmless phone recording. Your speech-recognition service must accept its format.

Phones cannot reach `127.0.0.1`. Bind intake to a private interface and restrict access with a firewall, or use a trusted private overlay network. No built-in authentication. Never expose intake to the internet.

1. Record audio or receive an audio file from the Share Sheet.
2. Generate `request_id`, a fresh lowercase UUID with hyphens. Reuse only for retries of identical saved audio.
3. New thread? Set `thread_id` to the same UUID. Follow-up? Use a saved thread ID, but a new request ID. Threads group notes. They do not give the formatter earlier conversation.
4. Add "Get Contents of URL":
   - URL: `http://<private-service-address>:8791/v1/voice-notes`
   - Method: `POST`
   - Request Body: Form
   - `audio`: File, recorded audio
   - `request_id`: Text, new UUID
   - `thread_id`: Text, selected UUID
   - Headers: none. Shortcuts sets `Content-Type` and the multipart boundary.
5. Show the response. HTTP `202`, `status: received` means saved, not transcribed.
6. Poll `GET http://<private-service-address>:8791/v1/jobs/<request_id>` for `completed` or `failed`. List recent threads with `GET http://<private-service-address>:8791/v1/threads?limit=10`.

`multipart form required`? Use Form body and File audio, not text. New request IDs submit new jobs. Retry the same recording with its original ID.
