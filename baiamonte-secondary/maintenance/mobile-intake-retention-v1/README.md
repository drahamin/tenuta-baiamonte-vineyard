# Mobile intake retention v1

Install this entire directory at the stable private path:

`/home/tenuoboe/apps/baiamonte-secondary/maintenance/mobile-intake-retention-v1`

Install its independent mode-0600 configuration at:

`/home/tenuoboe/apps/baiamonte-secondary/config/mobile-intake-retention-v1.php`

Neither path may be inside `public_html` or a versioned application release.
The scheduled command must point directly to this pinned maintenance version,
never through the `current` release symlink. The script needs only the existing
runtime CRUD rights on the four intake tables and `audit_events`; it does not
need DDL or the intake HMAC key.

Every run returns the complete retained-file inventory. `health.clear=true`
requires zero undeleted database evidence, missing or out-of-scope paths,
unreferenced `.bin` files, and staging files. `pending_cleanup=0` alone is not a
retention-clear signal.
