// Root search assembly (SPEC §7): candidates from the providers (Providers.js), metadata
// (alias, favourites, frecency), sections, and the actions each row offers.
// Ranking itself is Ranker.js; frecency maths is Frecency.js. Both are passed
// in as `deps` because a core module never imports another (QML + node).

var SUGGESTIONS_LIMIT = 6            // [I] SPEC §7.2 "N≈6"

// Attach per-user metadata. Returns new objects; inputs stay untouched.
function decorate(candidate, ctx, deps) {
  var out = {}
  for (var k in candidate) out[k] = candidate[k]
  var settings = (ctx.commands && ctx.commands[candidate.id]) || {}
  var visits = (ctx.frecency && ctx.frecency[candidate.id]) || null
  out.alias = settings.alias ? String(settings.alias).toLowerCase() : ""
  out.favoriteOrder = typeof settings.favoriteOrder === "number" ? settings.favoriteOrder : null
  out.frecency = visits ? deps.Frecency.score(visits.anchor, ctx.nowMs / 1000) : 1
  out.openedAt = visits ? visits.openedAt : null
  out.searchTerms = visits && visits.searchTerms ? visits.searchTerms : []
  return out
}

function isEnabled(candidate, ctx) {
  var settings = ctx.commands && ctx.commands[candidate.id]
  return !(settings && settings.enabled === false)
}

function rankOptions(ctx) {
  return { sensitivity: ctx.sensitivity || "medium", nowMs: ctx.nowMs }
}

// "Use … with…" rows: whatever the providers offer as fallbacks for this query.
function fallbackRows(query, ctx) {
  var rows = typeof ctx.fallbacks === "function" ? ctx.fallbacks(query) : []
  return rows.map(function(candidate) { return { candidate: candidate, record: null } })
}

// Sections for the root view (SPEC §7.2):
//   empty query: Favorites, Suggestions, Commands, Applications
//   query:       Results, Use "<q>" with…
function rootSections(candidates, query, ctx, deps) {
  var q = String(query || "").trim()
  var decorated = []
  for (var i = 0; i < candidates.length; i++) {
    if (!isEnabled(candidates[i], ctx)) continue
    decorated.push(decorate(candidates[i], ctx, deps))
  }
  var opts = rankOptions(ctx)

  if (q) {
    var searchable = decorated.filter(function(c) { return c.rootSearch.when !== "empty" })
    var results = deps.Ranker.rank(searchable, q, opts)
    var sections = []
    var answers = typeof ctx.answers === "function" ? ctx.answers(q) : []
    if (answers.length) sections.push({ id: "answers", title: "", rows: answers.map(function(candidate) { return { candidate: candidate, record: null } }) })
    if (results.length > 0) sections.push({ id: "results", title: "Results", rows: results })
    var fallbacks = fallbackRows(q, ctx)
    if (fallbacks.length) sections.push({ id: "fallback-commands", title: "Use “" + q + "” with…", rows: fallbacks })
    return sections
  }

  var shown = decorated.filter(function(c) { return c.rootSearch.when !== "searching" || c.favoriteOrder !== null })
  var taken = {}
  var favorites = shown.filter(function(c) { return c.favoriteOrder !== null })
    .sort(function(a, b) { return a.favoriteOrder - b.favoriteOrder })
  favorites.forEach(function(c) { taken[c.id] = true })

  var suggestions = deps.Ranker.rank(decorated.filter(function(c) { return !taken[c.id] && c.frecency > 1 }), "", opts)
    .slice(0, SUGGESTIONS_LIMIT)
  suggestions.forEach(function(r) { taken[r.candidate.id] = true })

  var rest = shown.filter(function(c) { return !taken[c.id] })
  var commands = deps.Ranker.rank(rest.filter(function(c) { return c.type !== "application" }), "", opts)
  var apps = deps.Ranker.rank(rest.filter(function(c) { return c.type === "application" }), "", opts)

  var out = []
  if (favorites.length) out.push({ id: "favorites", title: "Favorites", rows: favorites.map(function(c) { return { candidate: c, record: null } }) })
  if (suggestions.length) out.push({ id: "suggestions", title: "Suggestions", rows: suggestions })
  if (commands.length) out.push({ id: "commands", title: "Commands", rows: commands })
  if (apps.length) out.push({ id: "apps", title: "Applications", rows: apps })
  return out
}

// Actions for a row (SPEC §10.2 action panel, §10.3 shortcuts). `own` is what the
// row's provider offers; its first entry is primary (↵), the second secondary
// (Ctrl ↵). The generic actions below apply to every stored row.
function actionsFor(candidate, own) {
  var list = (own && own.length ? own : [{ id: "open", title: "Open Command" }]).map(function(action, i) {
    var copy = {}
    for (var k in action) copy[k] = action[k]
    if (i === 0) { copy.shortcut = "↵"; copy.section = "primary" }
    return copy
  })

  if (candidate.fallback || candidate.answer) return list

  if (candidate.favoriteOrder === null || candidate.favoriteOrder === undefined) {
    list.push({ id: "favorite-add", title: "Add to Favorites", shortcut: "Ctrl Shift F", section: "favorites", icon: "" })
  } else {
    list.push({ id: "favorite-remove", title: "Remove from Favorites", shortcut: "Ctrl Shift F", section: "favorites", icon: "" })
    list.push({ id: "favorite-up", title: "Move Up in Favorites", shortcut: "Ctrl Alt ↑", section: "favorites", icon: "" })
    list.push({ id: "favorite-down", title: "Move Down in Favorites", shortcut: "Ctrl Alt ↓", section: "favorites", icon: "" })
  }
  list.push({ id: "set-alias", title: candidate.alias ? "Change Alias" : "Set Alias", shortcut: "", section: "configure", icon: "" })
  if (candidate.alias) list.push({ id: "remove-alias", title: "Remove Alias", shortcut: "", section: "configure", icon: "" })
  if (candidate.frecency > 1) list.push({ id: "reset-ranking", title: "Reset Ranking", shortcut: "", section: "configure", icon: "" })
  list.push({ id: "disable", title: "Disable Command", shortcut: "Alt Shift D", section: "delete", icon: "" })
  return list
}

// Favourite ordering: returns the new {id: order} map for an action.
function reorderFavorites(commands, id, action) {
  var favs = []
  for (var key in commands) if (typeof commands[key].favoriteOrder === "number") favs.push({ id: key, order: commands[key].favoriteOrder })
  favs.sort(function(a, b) { return a.order - b.order })
  var ids = favs.map(function(f) { return f.id })
  var at = ids.indexOf(id)
  if (action === "favorite-add" && at < 0) ids.push(id)
  else if (action === "favorite-remove" && at >= 0) ids.splice(at, 1)
  else if (action === "favorite-up" && at > 0) { ids.splice(at, 1); ids.splice(at - 1, 0, id) }
  else if (action === "favorite-down" && at >= 0 && at < ids.length - 1) { ids.splice(at, 1); ids.splice(at + 1, 0, id) }
  var out = {}
  for (var i = 0; i < favs.length; i++) out[favs[i].id] = null
  for (var j = 0; j < ids.length; j++) out[ids[j]] = j
  return out
}

// Root view dropdown (Ctrl+P): one entry per candidate type, "All" first. [D]
function typeFilters(candidates, extra) {
  var seen = {}
  var labels = []
  for (var i = 0; i < candidates.length; i++) {
    var label = candidates[i].typeLabel
    if (label && !seen[label]) { seen[label] = true; labels.push(label) }
  }
  labels.sort()
  var types = labels.map(function(label) { return { id: label, title: label } })
  return [{ id: "", title: "All" }].concat(types, (extra || []).map(function(f) { return { id: f.id, title: f.title } }))
}

function filterByType(candidates, typeId) {
  if (!typeId) return candidates
  // "@<provider>:<category>" comes from a provider's own filters().
  if (typeId.charAt(0) === "@") {
    var at = typeId.indexOf(":")
    var provider = typeId.slice(1, at)
    var category = typeId.slice(at + 1)
    return candidates.filter(function(c) { return c.provider === provider && c.category === category })
  }
  return candidates.filter(function(c) { return c.typeLabel === typeId })
}

if (typeof module !== "undefined") {
  module.exports = {
    SUGGESTIONS_LIMIT: SUGGESTIONS_LIMIT,
    decorate: decorate,
    rootSections: rootSections,
    actionsFor: actionsFor,
    reorderFavorites: reorderFavorites,
    typeFilters: typeFilters,
    filterByType: filterByType
  }
}
