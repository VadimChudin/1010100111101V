# Storage Validation Record

- Railway production volume `app-volume` was created and mounted at `/data`.
- The backend now receives `STATE_DATABASE_PATH=/data/agent_state.db`.
- A controlled redeploy preserved the identical workspace snapshot, confirming durable volume persistence.
- The supplied Railway API token can create the volume and update variables but was denied (`Not Authorized`) when requesting the volume backup workflow.
- The authenticated Railway dashboard was opened to attempt the confirmed backup through the user session; it initially rendered a loading shell and needs a subsequent UI check before interacting with any backup control.

The Railway dashboard confirms that `app-volume` is online, attached to the `app` service at `/data`, and provisioned with a 500 MB limit in EU West. The volume settings page exposes mount, capacity, region, alerts, wipe, and deletion controls but no visible backup action; a text search for backup returned no result. The public backup API then returned `Not Authorized` for the supplied token, so an initial Railway-managed snapshot could not be created through either currently available route.
