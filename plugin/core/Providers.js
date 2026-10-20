// Root-search provider registry. A provider is where candidates come from and
// what happens when one is picked; the core never branches on a provider's
// identity, so adding a source means registering one object. Apps and web
// search are providers of their own, and extension plugins use the same shape.
//
// A provider is:
//   id                              unique, e.g. "apps"
//   candidates()                    stored rows for root search
//   actionsFor(candidate)           [{id, title, ...}]; the first is the primary action (↵)
//   perform(candidate, actionId, ctx)
//                                   -> outcome {close, push, toast, hud, visit} or undefined
//                                   when the action is not the provider's (generic actions follow)
//   fallbacks(query)                optional: rows for the "Use … with…" section
//   answers(query)                  optional: rows shown above the results for this exact query,
//                                   like a calculator's answer; they are not stored or ranked
//   filters()                       optional: [{id, title}] entries for the Ctrl+P dropdown; a
//                                   candidate belongs to one by carrying `category` = id
//
// Loaded by QML and node --test, so no imports; QML wires dependencies in.

function createRegistry() {
  return { providers: {}, order: [], errors: [] }
}

function register(registry, provider) {
  var id = String(provider && provider.id || "")
  if (!/^[a-z][a-z0-9-]*$/.test(id)) throw new Error("Invalid provider id " + id)
  if (registry.providers[id]) throw new Error("Provider already registered " + id)
  var required = ["candidates", "actionsFor", "perform"]
  for (var i = 0; i < required.length; i++) {
    if (typeof provider[required[i]] !== "function") throw new Error("Provider " + id + " lacks " + required[i] + "()")
  }
  registry.providers[id] = provider
  registry.order.push(id)
}

function unregister(registry, id) {
  delete registry.providers[id]
  registry.order = registry.order.filter(function(other) { return other !== id })
}

function get(registry, id) {
  return registry.providers[id] || null
}

// Diagnostics deliberately contain no provider exception text or row payloads.
function diagnostic(registry, id, what, message, row) {
  var error = { provider: id, during: what, error: message }
  if (row !== undefined) error.row = row
  registry.errors.push(error)
  if (registry.errors.length > 50) registry.errors.shift()
}

function jsonCopy(value) {
  return JSON.parse(JSON.stringify(value, function(key, item) {
    if (typeof item === "number" && !isFinite(item)) throw new Error("Non-finite JSON number")
    return item
  }))
}

function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value) }

// Invoke once, then isolate each row: one broken row must not hide its siblings.
function guardedList(registry, id, what, fn, normalize) {
  var list
  try { list = fn() } catch (e) {
    diagnostic(registry, id, what, "Provider invocation failed")
    return []
  }
  if (!Array.isArray(list)) {
    diagnostic(registry, id, what, "Expected list")
    return []
  }
  var out = []
  for (var i = 0; i < list.length; i++) {
    try {
      var row = jsonCopy(list[i])
      if (!object(row) || !row.id) throw new Error("Invalid row")
      out.push(normalize(row))
    } catch (e) {
      diagnostic(registry, id, what, "Invalid row", i)
    }
  }
  return out
}

function candidateRow(row, id, kind) {
  row.provider = id
  if (kind === "fallbacks") row.fallback = true
  if (kind === "answers") row.answer = true
  var root = object(row.rootSearch) ? row.rootSearch : {}
  if (["always", "empty", "searching"].indexOf(root.when) < 0) {
    root.when = kind === "candidates" ? "always" : "searching"
  }
  row.rootSearch = root
  return row
}

function candidateLists(registry, what, query) {
  var out = []
  for (var i = 0; i < registry.order.length; i++) {
    var id = registry.order[i]
    var provider = registry.providers[id]
    if (what !== "candidates" && typeof provider[what] !== "function") continue
    out = out.concat(guardedList(registry, id, what,
      function() { return what === "candidates" ? provider.candidates() : provider[what](query) },
      function(row) { return candidateRow(row, id, what) }))
  }
  return out
}

function candidates(registry) {
  return candidateLists(registry, "candidates")
}

function fallbacks(registry, query) {
  return candidateLists(registry, "fallbacks", query)
}

function answers(registry, query) {
  return candidateLists(registry, "answers", query)
}

// Dropdown entries from every provider, as {id: "@<provider>:<id>", title, provider}.
function filters(registry) {
  var out = []
  for (var i = 0; i < registry.order.length; i++) {
    var id = registry.order[i]
    var provider = registry.providers[id]
    if (typeof provider.filters !== "function") continue
    out = out.concat(guardedList(registry, id, "filters", function() { return provider.filters() }, function(row) {
      return { id: "@" + id + ":" + row.id, title: String(row.title || row.id), provider: id }
    }))
  }
  return out
}

function actionsFor(registry, candidate) {
  if (!object(candidate)) return []
  var provider = registry.providers[candidate.provider]
  if (!provider) return []
  return guardedList(registry, provider.id, "actionsFor", function() { return provider.actionsFor(jsonCopy(candidate)) }, function(row) {
    if (typeof row.id !== "string" || !row.id.trim() || typeof row.title !== "string" || !row.title.trim()) {
      throw new Error("Invalid action")
    }
    return row
  })
}

function perform(registry, candidate, actionId, ctx) {
  var provider = registry.providers[candidate.provider]
  if (!provider) throw new Error("No provider " + candidate.provider + " for " + candidate.id)
  return provider.perform(candidate, actionId, ctx)
}

if (typeof module !== "undefined") {
  module.exports = {
    createRegistry: createRegistry,
    register: register,
    unregister: unregister,
    get: get,
    candidates: candidates,
    fallbacks: fallbacks,
    filters: filters,
    answers: answers,
    actionsFor: actionsFor,
    perform: perform
  }
}
