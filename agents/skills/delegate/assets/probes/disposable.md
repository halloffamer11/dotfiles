# Objective

In a disposable browser (one your own browser tool launches, with no signed-in sessions), open https://example.com and read the page title; then open https://httpbin.org/forms/post, type the literal token `{{NONCE}}` into the "Customer name" field, submit the form, and read the value the response echoes back for that field.

Do not use web fetch, curl, URL readers, web search, or any built-in web tool, and do not fall back to them if browser tools are unavailable or fail.

# Definition of done

The final message is ONLY the return-schema JSON.
Inside `deliverable`, output exactly one marker on its own line:
- On pass (replace with actual title and echoed value without angle brackets):
BROWSER-PROBE PASS title=<title> echoed=<value>
- On fail:
BROWSER-PROBE FAIL: <one-line reason>
