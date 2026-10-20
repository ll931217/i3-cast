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

// A provider that throws must not take the launcher down: record and skip.
function guarded(registry, id, what, fn, fallback) {
  try { return fn() } catch (e) {
    registry.errors.push({ provider: id, during: what, error: String(e) })
    if (registry.errors.length > 50) registry.errors.shift()
    return fallback
  }
}

function tag(list, id) {
  var out = []
  for (var i = 0; i < (list || []).length; i++) {
    var c = list[i]
    if (!c || !c.id) continue
    c.provider = id
    out.push(c)
  }
  return out
}

function candidates(registry) {
  var out = []
  for (var i = 0; i < registry.order.length; i++) {
    var id = registry.order[i]
    var provider = registry.providers[id]
    out = out.concat(tag(guarded(registry, id, "candidates", function() { return provider.candidates() }, []), id))
  }
  return out
}

function fallbacks(registry, query) {
  var out = []
  for (var i = 0; i < registry.order.length; i++) {
    var id = registry.order[i]
    var provider = registry.providers[id]
    if (typeof provider.fallbacks !== "function") continue
    var rows = tag(guarded(registry, id, "fallbacks", function() { return provider.fallbacks(query) }, []), id)
    rows.forEach(function(c) { c.fallback = true })
    out = out.concat(rows)
  }
  return out
}

// Dropdown entries from every provider, as {id: "@<provider>:<id>", title, provider}.
function filters(registry) {
  var out = []
  for (var i = 0; i < registry.order.length; i++) {
    var id = registry.order[i]
    var provider = registry.providers[id]
    if (typeof provider.filters !== "function") continue
    var items = guarded(registry, id, "filters", function() { return provider.filters() }, [])
    items.forEach(function(f) { if (f && f.id) out.push({ id: "@" + id + ":" + f.id, title: String(f.title || f.id), provider: id }) })
  }
  return out
}

function findFallback(registry, id) {
  var rows = fallbacks(registry, "")
  for (var i = 0; i < rows.length; i++) if (rows[i].id === id) return rows[i]
  return null
}

function actionsFor(registry, candidate) {
  var provider = registry.providers[candidate.provider]
  if (!provider) return []
  return guarded(registry, provider.id, "actionsFor", function() { return provider.actionsFor(candidate) }, [])
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
    findFallback: findFallback,
    actionsFor: actionsFor,
    perform: perform
  }
}
