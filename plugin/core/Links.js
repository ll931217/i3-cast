// raycast:// deep links (SPEC §5.5), mapped onto x-cast commands. x-cast has no Raycast
// extension runtime, so a link works when a local command (a script command or an app) carries
// the same slug as the link's <command>; otherwise it opens the launcher with that name as the query.
//
//   raycast://extensions/<owner>/<extension>/<command>?arguments=<url-encoded JSON>
//   raycast://script-commands/<command>?arguments=<url-encoded JSON>
//
// `arguments` is an object keyed by argument name (argument1..3 for script commands) or an array.

function slug(text) {
  return String(text || "").toLowerCase().replace(/\.desktop$/, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")
}

function decode(part) {
  try { return decodeURIComponent(part) } catch (e) { return part }
}

function parseArguments(raw) {
  if (!raw) return null
  try {
    var value = JSON.parse(decode(raw))
    return value && typeof value === "object" ? value : null
  } catch (e) { return null }
}

// -> {command, extension, arguments} or null when the URL is not a command link.
function parse(url) {
  var m = /^raycast:\/\/([^?#]*)(?:\?([^#]*))?/.exec(String(url || ""))
  if (!m) return null
  var parts = m[1].split("/").filter(function(p) { return p }).map(decode)
  var query = {}
  String(m[2] || "").split("&").forEach(function(pair) {
    var at = pair.indexOf("=")
    if (at > 0) query[pair.slice(0, at)] = pair.slice(at + 1)
  })
  var args = parseArguments(query.arguments)
  if (parts[0] === "extensions" && parts.length >= 4) return { command: slug(parts[3]), extension: slug(parts[2]), arguments: args }
  if (parts[0] === "script-commands" && parts.length >= 2) return { command: slug(parts[1]), extension: "", arguments: args }
  return null
}

// The link's argument values in the candidate's pill order.
function argumentValues(specs, given) {
  return (specs || []).map(function(spec, i) {
    var value = Array.isArray(given) ? given[i] : given ? given[spec.name] : ""
    return value === undefined || value === null ? "" : String(value)
  })
}

// The best candidate for a link: same command slug, preferring one whose package or subtitle matches the extension.
function resolve(candidates, link) {
  var found = candidates.filter(function(c) { return slug(c.title) === link.command })
  if (found.length === 0) return null
  var better = found.filter(function(c) { return link.extension && slug(c.subtitle) === link.extension })
  var candidate = (better.length ? better : found)[0]
  var values = argumentValues(candidate.arguments, link.arguments)
  var missing = false
  ;(candidate.arguments || []).forEach(function(spec, i) { if (!spec.optional && !values[i]) missing = true })
  return { candidate: candidate, arguments: values, missingArguments: missing }
}

if (typeof module !== "undefined") module.exports = { slug: slug, parse: parse, resolve: resolve, argumentValues: argumentValues }
