Capability probe, not a real task. Do not delegate. No file edits.

Using a real browser-automation tool that you control (for example a
Playwright MCP server: browser_navigate, then browser_snapshot), open
https://example.com and read the page's h1 element.

The browser must be a fresh instance you launch and control yourself — a
disposable browser with no cookies or logged-in sessions. The user's
already-running browser does NOT count for this probe: if your only browser
access is an extension or native-host connection to the user's live
browser, report failure.

You must NOT use plain HTTP fetch, URL-reader, or web-search tools
(read_url_content, web.run, search_web, curl, or similar). If no browser
tool is available, or the browser tool is denied or fails, do NOT fall back
to fetching — report the failure instead.

If the browser tool works, print exactly:
UNAUTH-BROWSER-OK via <tool>: <h1 text>

Otherwise print exactly:
UNAUTH-BROWSER-FAIL: <one-line reason>
