# Objective

In the agent profile (the user's signed-in agent browser profile reached through a browser extension; a browser you launch yourself does not count), open https://www.facebook.com/marketplace and report the signed-in account name shown. Click nothing and type nothing that changes state.

Forbid web fetch, curl, URL readers, web search, and every built-in web tool. Do not fall back to them if the agent profile or browser extension is unavailable or fails.

# Definition of done

The final message is ONLY the return-schema JSON.
Inside `deliverable`, output exactly one marker on its own line:
- On pass (replace with actual account name without angle brackets):
BROWSER-PROBE PASS account=<name>
- On fail:
BROWSER-PROBE FAIL: <one-line reason>
