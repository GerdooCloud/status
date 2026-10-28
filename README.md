# External Gerdoo status page

The external monitor is `GerdooCloud/status` on GitHub Pages. Its source
contains only this public page, external probes, public incident/history data,
and fonts/icons. The private Gerdoo repository is never published.

`status.yml` is installed as `.github/workflows/status.yml` in that repository.
The other files in this directory are installed at its root, alongside
`assets/fonts/YekanBakh-VF.woff2`, `assets/favicon.svg`, and `assets/favicon.ico`
copied from `deploy/get`. Make future status-page and incident changes in the
standalone repository; this directory records the migration source.

## Monitoring and incidents

GitHub-hosted runners probe the panel, public application gateway (with TLS
verification), and Gerdoo's authoritative DNS directly. They also mirror the
original public history and incidents from `https://api.gerdoo.cloud/api/status/history`.
The page retains the original four components, including deployment operations.
That internal component uses the fresh API snapshot; it becomes unknown if the
API is unavailable. The last successful history remains stored externally, and
the other three probes continue independently during a Gerdoo outage.

Checks run approximately every five minutes, retry failures once, and keep
90 days of sample counts in the `status-data` branch. GitHub Actions can delay
or skip scheduled jobs; the page shows unknown status after 20 minutes without
a new sample. History bars follow the original page's incident/outage colors.
Green means no recorded incident or confirmed outage, including before probe
records began; it does not establish measured uptime for unobserved days.
Failed samples estimate five minutes of
unavailability each; gaps between jobs are not counted as confirmed uptime or
downtime. Uptime percentages use the original hourly buckets and include
declared incidents, with overlapping intervals counted once. Exported historical
outage percentages are preserved; the export does not contain their exact spans.
This is basic monitoring, not a guaranteed one-minute alerting service.

`history.json` archives the old public snapshot and seeds daily probe counts
once. `incidents.json` holds the exported public incidents. The existing Gerdoo
admin incident editor is mirrored on the next successful history sync. Add or
edit incidents in `incidents.json` and commit to `main` to publish manual
overrides even when Gerdoo is unavailable.
Keep the existing incident JSON shape, timestamps, and numeric IDs; use the
component keys from `monitor.py`. Old incidents may refer to `k8s_cluster`.

Enable scheduled workflows again if GitHub disables them after inactivity.
Watch failed workflow runs: a broken monitor/deployment must not silently be
treated as healthy. A private repository would require a paid GitHub Pages plan.

## Domain and cutover

The user handles static hosting and DNS on Arvan. The upload bundle is
`artifacts/gerdoo-status-arvan.zip` in the Gerdoo workspace. Upload its contents
to the static site root, retaining `fonts/`, and attach `gerdoocloudstatus.ir`
with HTTPS through Arvan. No server process or build command is required.

The Arvan bundle sets the `status-data-url` HTML meta tag to
`https://gerdoocloud.github.io/status/status.json`. GitHub Pages serves this
public JSON with CORS enabled, so the independently hosted HTML can fetch fresh
monitoring data. Do not set a custom domain on the GitHub Pages site: the Arvan
page relies on this stable JSON URL. Only cache static assets on Arvan; JSON is
requested directly from GitHub with a per-minute query parameter to bypass
GitHub Pages' ten-minute shared cache. The original page and GitHub-hosted preview
leave the meta tag empty to use their own data endpoint.

The GitHub-hosted preview is `https://gerdoocloud.github.io/status/`.

After HTTPS and fresh external checks work on the new domain:

1. Update public links in `landing/src/components/layout/Footer.tsx`,
   `landing/src/pages/info/About.tsx`, and `admin/src/pages/StatusIncidents.tsx`.
2. Change both `/support/status` redirects in `deploy/Caddyfile` to the new domain.
3. Replace the old `status.gerdoo.cloud` site body with
   `redir https://gerdoocloudstatus.ir{uri} permanent`.
4. Update the status-page URL in `backend/internal/handlers/status_outages.go`.
   Internal probes and admin incident history can remain for internal use.
5. Deploy and verify redirects. Remove the `/srv/status` Compose mount later.

These redirects intentionally wait until the destination is live. Roll back
by restoring the old Caddy site block and links; the backend history and old
page are retained.

## Local checks

```sh
python3 -m unittest discover -s deploy/status -p test_monitor.py -v
python3 deploy/status/monitor.py --state /tmp/status-state.json \
  --output /tmp/status-public --assets deploy/get
python3 -m http.server --directory /tmp/status-public 8088
```

The standalone repository uses `python3 -m unittest -v test_monitor.py` and
`python3 monitor.py --state /tmp/state.json --output public`.
