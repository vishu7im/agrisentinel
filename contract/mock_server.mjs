/**
 * AgriSentinel mock server — Phase 0.
 *
 * Serves contract/mock_run.json on the four endpoints in endpoints.md so Dev B can build
 * the entire frontend before Dev A's backend exists. At M1, point VITE_API_URL at the real
 * backend instead and nothing else changes.
 *
 *   node contract/mock_server.mjs [--fast|--slow|--interval=MS] [--block] [--port=N]
 *
 * Node built-ins only. No npm install, ever.
 *
 * NOTE: this file is the one thing inside contract/ that is NOT frozen. It is a dev tool,
 * not the contract. Dev B may fix it freely. run_state.schema.json and mock_run.json are
 * the frozen artefacts.
 */

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------- args

const argv = process.argv.slice(2);
const has = (f) => argv.includes(f);
const valOf = (name, fallback) => {
  const hit = argv.find((a) => a.startsWith(`--${name}=`) || a === `--${name}`);
  if (!hit) return fallback;
  if (hit.includes("=")) return hit.split("=")[1];
  return argv[argv.indexOf(hit) + 1] ?? fallback; // support "--port 8010"
};

const PORT = Number(valOf("port", 8000));
const BLOCK_MODE = has("--block");
const INTERVAL = Number(
  valOf("interval", has("--fast") ? 150 : has("--slow") ? 2000 : 1000)
);

// ---------------------------------------------------------------- data

const BASE_RUN = JSON.parse(
  readFileSync(join(HERE, "mock_run.json"), "utf8")
);

/**
 * The BLOCK variant, derived from the PASS run rather than kept as a second fixture —
 * so the two can never drift apart. This is the state Dev B's B6 refusal card renders:
 * the diagnosis and severity survive, the treatment advice does not.
 */
function toBlocked(run) {
  const blocked = structuredClone(run);
  blocked.status = "blocked";
  blocked.plan_draft = null;
  blocked.schedule = null;
  blocked.cost_estimate = null;
  blocked.rescan_date = null;
  blocked.verification = {
    status: "BLOCK",
    unsupported_claims: [
      "Apply copper oxychloride combined with a systemic triazole at double the label rate for faster knockdown.",
      "A single application is sufficient to eradicate the infection.",
    ],
    sources: run.verification.sources.slice(0, 2),
    block_reason:
      "The drafted plan named a chemical combination that is not in the verified agronomy corpus, at a rate above any cited label range. Treatment advice was withheld rather than issued unverified.",
  };
  blocked.report = {
    en: "Your tomato field has late blight. About 18 out of every 100 plants we checked are affected, spread across three patches. The disease is moving towards the north-east corner. We are not giving a spray recommendation for this case, because we could not confirm one against our verified sources. Please show this result to your local agriculture extension officer. Do not spray on guesswork.",
    hi: "आपके टमाटर के खेत में पछेती झुलसा (लेट ब्लाइट) रोग लगा है। जाँचे गए हर 100 पौधों में से लगभग 18 पौधे प्रभावित हैं, जो तीन जगह फैले हैं। रोग खेत के उत्तर-पूर्व कोने की ओर बढ़ रहा है। इस मामले में हम छिड़काव की सलाह नहीं दे रहे हैं, क्योंकि हम इसे अपने प्रमाणित स्रोतों से पुष्ट नहीं कर सके। कृपया यह परिणाम अपने स्थानीय कृषि विस्तार अधिकारी को दिखाएँ। अनुमान के आधार पर छिड़काव न करें।",
  };
  const cut = run.events.indexOf("agronomist.done");
  blocked.events = [
    ...run.events.slice(0, cut + 1),
    "verify.block",
    "reporter.done",
    "run.complete",
  ];
  return blocked;
}

const RUN = BLOCK_MODE ? toBlocked(BASE_RUN) : BASE_RUN;

/** Placeholder field mosaic so image_url resolves and the heatmap has a backing image. */
const PLACEHOLDER_IMAGE = `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600">
  <defs>
    <linearGradient id="soil" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3f5d23"/><stop offset="100%" stop-color="#2a3d18"/>
    </linearGradient>
    <pattern id="rows" width="24" height="24" patternUnits="userSpaceOnUse">
      <rect width="24" height="24" fill="none"/>
      <circle cx="12" cy="12" r="7" fill="#4e7a2a" opacity="0.55"/>
    </pattern>
  </defs>
  <rect width="960" height="600" fill="url(#soil)"/>
  <rect width="960" height="600" fill="url(#rows)"/>
  <rect y="480" width="120" height="120" fill="#6b5636" opacity="0.85"/>
  <rect x="840" y="480" width="120" height="120" fill="#6b5636" opacity="0.85"/>
  <text x="480" y="308" font-family="monospace" font-size="26" fill="#c8dba8"
        text-anchor="middle" opacity="0.6">mock field mosaic — 8 x 5</text>
</svg>`;

// ---------------------------------------------------------------- http

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const sendJson = (res, code, body) => {
  const payload = JSON.stringify(body, null, 2);
  res.writeHead(code, {
    ...CORS,
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
    "Cache-Control": "no-store",
  });
  res.end(payload);
};

/** The mock accepts any run_id and echoes it back, so the client's stored id always matches. */
const runFor = (id) => ({ ...RUN, run_id: id, image_url: `/api/run/${id}/image` });

function streamEvents(res, id) {
  res.writeHead(200, {
    ...CORS,
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });

  const events = RUN.events;
  let i = 0;
  console.log(`  -> SSE open  ${id}  (${events.length} events @ ${INTERVAL}ms)`);

  const timer = setInterval(() => {
    if (i >= events.length) {
      clearInterval(timer);
      console.log(`  -> SSE done  ${id}`);
      res.end();
      return;
    }
    res.write(`data: ${events[i++]}\n\n`);
  }, INTERVAL);

  res.on("close", () => clearInterval(timer));
}

const server = createServer((req, res) => {
  const { pathname } = new URL(req.url, `http://${req.headers.host}`);
  console.log(`${req.method} ${pathname}`);

  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS);
    return res.end();
  }

  if (req.method === "GET" && pathname === "/api/health") {
    return sendJson(res, 200, { status: "ok" });
  }

  if (req.method === "POST" && pathname === "/api/run") {
    // The upload is deliberately consumed and discarded — the mock always replays the
    // same run regardless of which image you send.
    req.resume();
    return req.on("end", () =>
      sendJson(res, 202, { run_id: crypto.randomUUID() })
    );
  }

  const events = pathname.match(/^\/api\/run\/([^/]+)\/events$/);
  if (req.method === "GET" && events) {
    return streamEvents(res, events[1]);
  }

  const image = pathname.match(/^\/api\/run\/([^/]+)\/image$/);
  if (req.method === "GET" && image) {
    res.writeHead(200, {
      ...CORS,
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "no-store",
    });
    return res.end(PLACEHOLDER_IMAGE);
  }

  const run = pathname.match(/^\/api\/run\/([^/]+)$/);
  if (req.method === "GET" && run) {
    return sendJson(res, 200, runFor(run[1]));
  }

  sendJson(res, 404, { detail: `no route for ${req.method} ${pathname}` });
});

server.listen(PORT, () => {
  const mode = BLOCK_MODE ? "BLOCK (verifier refuses)" : "PASS (plan revised, then verified)";
  console.log(`
  AgriSentinel mock server
  http://localhost:${PORT}

  mode      ${mode}
  events    ${RUN.events.length} @ ${INTERVAL}ms  (~${Math.round((RUN.events.length * INTERVAL) / 1000)}s per run)

  POST /api/run              -> { run_id }
  GET  /api/run/:id          -> full run state
  GET  /api/run/:id/events   -> SSE
  GET  /api/run/:id/image    -> placeholder field mosaic
  GET  /api/health           -> { status: "ok" }

  --fast / --slow / --interval=MS   change replay speed
  --block                           serve the refusal case
  --port=N                          if 8000 is taken (the real backend wants it too)
`);
});
