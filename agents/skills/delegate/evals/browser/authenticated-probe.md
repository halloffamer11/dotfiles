Capability probe, not a real task. Do not delegate. No file edits.

Demonstrate access to the user's live, logged-in browser session through
your browser integration (browser extension, native messaging host, or
connected-browser tools). A browser you launch yourself does NOT count,
and fetching pages over HTTP does NOT count.

Two accepted demonstrations — use whichever your integration supports:
(a) List the titles of the tabs currently open in the user's browser; or
(b) if your integration cannot enumerate existing tabs, open ONE new tab,
    navigate it to https://example.com, read the page's h1, and close the
    tab you opened.

Strict limits: never touch, navigate, refresh, or close any existing tab;
open at most the single tab in (b); no navigation beyond example.com.

If you succeed, print exactly:
AUTH-BROWSER-OK via <mechanism>
followed by the tab titles (for a) or the h1 text (for b), one per line.

If you cannot, print exactly:
AUTH-BROWSER-FAIL: <one-line reason>
and stop. Do not fall back to any other method.
