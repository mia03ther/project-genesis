# iPhone private playtest plan

The immediate target is Safari on iPhone, with the game and API served together from the PC. This does not require TestFlight or an App Store release. The PC must remain awake. Single-user sessions mean the phone and desktop share the same attempt; do not play simultaneously.

Recommended connection: install Tailscale on Windows and iPhone, sign in to the same private network, and use Tailscale Serve as an HTTPS reverse proxy. Anvil and Python continue listening on loopback. No campus router port forwarding is assumed. Official reference: https://tailscale.com/docs/reference/tailscale-cli/serve

This machine currently has no detected tailscale command. Installation/login and an actual phone connection have NOT been performed. Before enabling Serve, add the exact assigned private HTTPS hostname to the lab's allowed-host configuration; the current default intentionally refuses external Host headers. Do not use a wildcard allowed host. A follow-up should implement the exact-host CLI setting and same-origin checks before enabling this route. Do not expose Anvil or use a public Funnel link for the current single-user lab.

Once configured and tested: run the built game backend, proxy only its HTTP port, open the displayed private HTTPS address in Safari, and optionally use Share > Add to Home Screen. Test touch targets, portrait safe areas, copy buttons, disconnect/reconnect, duplicate taps and reset after replay. No iPhone verification is claimed here.
