# External Gerdoo status page

The standalone deployment is `GerdooCloud/status` on GitHub Pages. Its source
contains only this public page, external probes, public incident/history data,
and fonts/icons. The private Gerdoo repository is never published.

`status.yml` is installed as `.github/workflows/status.yml` in that repository.
The other files in this directory are installed at its root, alongside
`assets/fonts/YekanBakh-VF.woff2`, `assets/favicon.svg`, and `assets/favicon.ico`
copied from `deploy/get`. Make future status-page and incident changes in the
standalone repository; this directory records the migration source.

## Monitoring and incidents

GitHub-hosted runners probe the panel, API readiness, public application gateway
(with TLS verification), and Gerdoo's authoritative DNS directly. No Gerdoo API
is needed to serve the status page or record these checks. Kubernetes deployment
operations cannot be checked from outside the cluster, so that component is
retained only in the history export, not presented as externally monitored.

Checks run approximately every five minutes, retry failures once, and keep
90 days of sample counts in the `status-data` branch. GitHub Actions can delay
or skip scheduled jobs; the page shows unknown status after 20 minutes without
a new sample. Missing days are grey. Failed samples estimate five minutes of
unavailability each; gaps between jobs are not counted as confirmed uptime or
downtime. Uptime percentages are sample based; the old page used hourly buckets.
This is basic monitoring, not a guaranteed one-minute alerting service.

`history.json` archives the old public snapshot and seeds daily probe counts
once. `incidents.json` holds the exported public incidents. Add incident updates
there and commit to `main` to publish them, even when Gerdoo is unavailable.
The existing Gerdoo admin incident editor does not publish to this external page.
Keep the existing incident JSON shape, timestamps, and numeric IDs; use the
component keys from `monitor.py`. Old incidents may refer to `k8s_cluster`.

Enable scheduled workflows again if GitHub disables them after inactivity.
Watch failed workflow runs: a broken monitor/deployment must not silently be
treated as healthy. A private repository would require a paid GitHub Pages plan.

## Domain and cutover

Configure GitHub Pages to publish via GitHub Actions. Initially verify the page
at `https://gerdoocloud.github.io/status/`, including `status.json` and fonts.

Set the Pages custom domain to `gerdoocloudstatus.ir`. In the domain's independent
Arvan DNS zone, add the four GitHub Pages apex A records from
[GitHub's current domain instructions](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).
Do not point the domain at Gerdoo or enable a CDN proxy while verifying Pages.
Verify ownership with GitHub's account-specific TXT record, and enable Enforce
HTTPS once GitHub provisions the certificate. Do not replace the existing MX,
TXT, or other unrelated records.

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
