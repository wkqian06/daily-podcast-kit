/**
 * Private podcast feed on Cloudflare Workers + R2.
 *
 * Routes (all under a secret token so the feed is unlisted, not public):
 *   GET  /f/<TOKEN>/feed.xml            the RSS feed
 *   GET  /f/<TOKEN>/a/<key>             audio, with byte-range support
 *   GET  /f/<TOKEN>/c/<key>             captions (WebVTT)
 *   POST /upload/<key>                  publish an object   (Bearer UPLOAD_TOKEN)
 *   POST /manifest                      replace the episode list (Bearer UPLOAD_TOKEN)
 *   GET  /health
 *
 * Why the Worker serves the audio itself rather than handing out a storage URL:
 * podcast clients seek, so they issue Range requests, and some of them reuse a redirect
 * target across requests. A pre-signed URL bound to one range then fails on the second
 * request and the player stalls forever with no error. Serving through the Worker keeps
 * one stable URL and lets R2 answer each range directly.
 */

const XML_ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => XML_ESC[c]);

function unauthorized() {
  return new Response("Not found", { status: 404 });   // don't confirm the path exists
}

/** Encode each path segment but keep the slashes: some clients refuse %2F in a path. */
function encPath(key) {
  return String(key).split("/").map(encodeURIComponent).join("/");
}

function rfc2822(dateStr) {
  const d = new Date(dateStr + "T12:00:00Z");
  return isNaN(d) ? new Date().toUTCString() : d.toUTCString();
}

function hhmmss(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`
           : `${m}:${String(r).padStart(2, "0")}`;
}

function buildFeed(manifest, base, env) {
  const ch = manifest.channel || {};
  const items = (manifest.episodes || [])
    .slice()
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .map((ep) => {
      const audio = `${base}/a/${encPath(ep.audio_key)}`;
      const caption = ep.caption_key
        ? `\n      <podcast:transcript url="${esc(base)}/c/${encPath(ep.caption_key)}" type="text/vtt" language="en" />`
        : "";
      return `
    <item>
      <title>${esc(ep.title)}</title>
      <description><![CDATA[${ep.summary || ""}]]></description>
      <itunes:summary><![CDATA[${ep.summary || ""}]]></itunes:summary>
      <itunes:subtitle>${esc(ep.subtitle || "")}</itunes:subtitle>
      <guid isPermaLink="false">${esc(ep.guid || ep.audio_key)}</guid>
      <pubDate>${rfc2822(ep.date)}</pubDate>
      <enclosure url="${esc(audio)}" length="${ep.bytes || 0}" type="${esc(ep.mime || "audio/mp4")}" />
      <itunes:duration>${hhmmss(ep.seconds)}</itunes:duration>
      <itunes:episode>${ep.number || ""}</itunes:episode>
      <itunes:explicit>false</itunes:explicit>${caption}
    </item>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:podcast="https://podcastindex.org/namespace/1.0"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${esc(ch.title || env.FEED_TITLE || "Private Podcast")}</title>
    <link>${esc(ch.link || base)}</link>
    <description><![CDATA[${ch.description || "A private feed."}]]></description>
    <language>${esc(ch.language || "en")}</language>
    <itunes:author>${esc(ch.author || "")}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:block>Yes</itunes:block>
    <atom:link href="${esc(base)}/feed.xml" rel="self" type="application/rss+xml" />
    ${ch.image ? `<itunes:image href="${esc(ch.image)}" />` : ""}
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>${items}
  </channel>
</rss>
`;
}

/** Serve an R2 object, honouring Range so clients can seek. */
async function serveObject(env, key, request, fallbackType) {
  const range = request.headers.get("range");
  let opts = {};
  let parsed = null;

  if (range) {
    const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
    if (m) {
      const head = await env.BUCKET.head(key);
      if (!head) return new Response("Not found", { status: 404 });
      const size = head.size;
      let start, end;
      if (m[1] === "") {                       // suffix range: last N bytes
        const n = parseInt(m[2], 10);
        start = Math.max(0, size - n);
        end = size - 1;
      } else {
        start = parseInt(m[1], 10);
        end = m[2] === "" ? size - 1 : Math.min(parseInt(m[2], 10), size - 1);
      }
      if (start > end || start >= size) {
        return new Response("Range Not Satisfiable", {
          status: 416, headers: { "content-range": `bytes */${size}` },
        });
      }
      opts = { range: { offset: start, length: end - start + 1 } };
      parsed = { start, end, size };
    }
  }

  const obj = await env.BUCKET.get(key, opts);
  if (!obj) return new Response("Not found", { status: 404 });

  const h = new Headers();
  obj.writeHttpMetadata(h);
  h.set("etag", obj.httpEtag);
  h.set("accept-ranges", "bytes");
  h.set("cache-control", "private, max-age=3600");
  if (!h.get("content-type")) h.set("content-type", fallbackType);

  if (parsed) {
    h.set("content-range", `bytes ${parsed.start}-${parsed.end}/${parsed.size}`);
    h.set("content-length", String(parsed.end - parsed.start + 1));
    return new Response(obj.body, { status: 206, headers: h });
  }
  h.set("content-length", String(obj.size));
  return new Response(obj.body, { status: 200, headers: h });
}

function bearerOk(request, env) {
  const a = request.headers.get("authorization") || "";
  const t = a.startsWith("Bearer ") ? a.slice(7) : "";
  return env.UPLOAD_TOKEN && t === env.UPLOAD_TOKEN;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname);

    if (path === "/health") return new Response("ok\n");

    // ---- publishing endpoints -------------------------------------------------
    if (path.startsWith("/upload/")) {
      if (request.method !== "PUT" && request.method !== "POST")
        return new Response("Method not allowed", { status: 405 });
      if (!bearerOk(request, env)) return unauthorized();
      const key = path.slice("/upload/".length);
      if (!key) return new Response("Missing key", { status: 400 });
      await env.BUCKET.put(key, request.body, {
        httpMetadata: {
          contentType: request.headers.get("content-type") || "application/octet-stream",
        },
      });
      const head = await env.BUCKET.head(key);
      return Response.json({ ok: true, key, bytes: head?.size ?? null });
    }

    if (path === "/manifest") {
      if (!bearerOk(request, env)) return unauthorized();
      if (request.method === "POST" || request.method === "PUT") {
        const body = await request.text();
        try { JSON.parse(body); } catch { return new Response("Invalid JSON", { status: 400 }); }
        await env.BUCKET.put("manifest.json", body, {
          httpMetadata: { contentType: "application/json" },
        });
        return Response.json({ ok: true });
      }
      return new Response("Method not allowed", { status: 405 });
    }

    // ---- private feed ---------------------------------------------------------
    const m = /^\/f\/([^/]+)(\/.*)?$/.exec(path);
    if (!m) return unauthorized();
    const [, token, rest = "/"] = m;
    if (!env.FEED_TOKEN || token !== env.FEED_TOKEN) return unauthorized();

    const base = `${url.origin}/f/${token}`;

    if (rest === "/feed.xml" || rest === "/" || rest === "") {
      const obj = await env.BUCKET.get("manifest.json");
      if (!obj) return new Response("No manifest yet", { status: 404 });
      const manifest = await obj.json();
      return new Response(buildFeed(manifest, base, env), {
        headers: {
          "content-type": "application/rss+xml; charset=utf-8",
          "cache-control": "private, max-age=300",
        },
      });
    }

    if (rest.startsWith("/a/")) return serveObject(env, rest.slice(3), request, "audio/mp4");
    if (rest.startsWith("/c/")) return serveObject(env, rest.slice(3), request, "text/vtt");

    return unauthorized();
  },
};
