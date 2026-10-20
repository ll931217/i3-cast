// Persisted documents and their migrations. Each entry is one JSON file
// under $XDG_DATA_HOME/x-cast/db/. Add a migration to the end of a list;
// never edit or reorder one that has shipped.

// General settings, using Raycast's key names and defaults
// (reference/04 §3, App. C). [O] values unless marked.
var settingsMigrations = [
  {
    version: 1,
    name: "general-settings",
    up: function(doc) {
      doc.general = {
        windowMode: "expanded",                   // expanded | compact
        showFavoritesInCompactMode: true,
        windowPresentationMode: "mouse-screen",   // mouse-screen | active-screen | primary-screen
        popToRootTimeout: 90,                     // seconds: 0,5,15,30,60,90,120,180
        escapeKeyBehavior: "pop-back-or-close",   // pop-back-or-close | close-and-pop-to-root
        navigationBindings: "emacs",              // emacs | vim-motions
        rootSearchSensitivity: "medium",          // low | medium | high; backend default [O], SPEC §7.3
        uiZoom: 1
      }
      doc.commands = {}                           // commandId -> {enabled, alias, hotkey, favoriteOrder, fallbackOrder, meta}
      return doc
    }
  }
]

// Root-search ranking state (SPEC §6.4 `frecency`): per item an anchor in
// Unix seconds (Frecency.js), when it was last opened, and the queries that
// launched it. `searchHistory` backs ↑ in an empty root (SPEC §7.5).
var frecencyMigrations = [
  {
    version: 1,
    name: "frecency",
    up: function(doc) {
      doc.items = {}            // itemId -> {anchor, openedAt, searchTerms: [{term, at}]}
      doc.searchHistory = []    // newest first, unique, capped
      return doc
    }
  }
]

var SEARCH_HISTORY_LIMIT = 20   // [I]

function pushSearchHistory(history, query) {
  var q = String(query || "").trim()
  var list = Array.isArray(history) ? history.slice() : []
  if (!q) return list
  list = list.filter(function(item) { return item !== q })
  list.unshift(q)
  return list.slice(0, SEARCH_HISTORY_LIMIT)
}

var documents = {
  settings: { file: "settings.json", migrations: settingsMigrations },
  frecency: { file: "frecency.json", migrations: frecencyMigrations }
}

// User options from $XDG_CONFIG_HOME/x-cast/config.yaml (the host parses the
// YAML and hands over camelCased keys). Not migrated; unknown keys are ignored,
// missing or wrongly typed ones fall back to these defaults.
var configDefaults = {
  logLevel: "info",                    // trace | debug | info | warning | error | fatal
  keepVisibleOnFocusLoss: false,       // dev aid (keepMainWindowVisibleOnResignKey)
  general: {},                         // overrides for the general settings above, same key names
  fallbacks: null                      // [{title, url}] with {query} in url; null keeps the built-in list
}

var generalTypes = {
  windowMode: ["expanded", "compact"],
  windowPresentationMode: ["mouse-screen", "active-screen", "primary-screen"],
  escapeKeyBehavior: ["pop-back-or-close", "close-and-pop-to-root"],
  navigationBindings: ["emacs", "vim-motions"],
  rootSearchSensitivity: ["low", "medium", "high"]
}

// The settings window is generated from this: one row per field, cycling through `options`.
var generalFields = [
  { key: "windowMode", title: "Window mode", options: generalTypes.windowMode },
  { key: "showFavoritesInCompactMode", title: "Show favorites in compact mode", options: [true, false] },
  { key: "windowPresentationMode", title: "Open on", options: generalTypes.windowPresentationMode },
  { key: "popToRootTimeout", title: "Return to root after (seconds)", options: [0, 5, 15, 30, 60, 90, 120, 180] },
  { key: "escapeKeyBehavior", title: "Escape key", options: generalTypes.escapeKeyBehavior },
  { key: "navigationBindings", title: "Navigation keys", options: generalTypes.navigationBindings },
  { key: "rootSearchSensitivity", title: "Search sensitivity", options: generalTypes.rootSearchSensitivity },
  { key: "uiZoom", title: "Interface zoom", options: [0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5] }
]

// Keep only general overrides that match the shipped defaults in type (and enum value).
function validGeneral(value, defaults) {
  var out = {}
  if (!value || typeof value !== "object") return out
  for (var k in value) {
    if (defaults[k] === undefined || typeof value[k] !== typeof defaults[k]) continue
    if (generalTypes[k] && generalTypes[k].indexOf(value[k]) < 0) continue
    out[k] = value[k]
  }
  return out
}

function validFallbacks(list) {
  if (!Array.isArray(list)) return null
  var out = []
  for (var i = 0; i < list.length; i++) {
    var f = list[i]
    if (!f || typeof f.title !== "string" || typeof f.url !== "string" || f.url.indexOf("{query}") < 0) continue
    out.push({ id: "fallback:" + out.length, title: f.title, icon: "", url: f.url })
  }
  return out.length ? out : null
}

function withConfigDefaults(value) {
  var out = {}
  for (var key in configDefaults) out[key] = configDefaults[key]
  if (value && typeof value === "object" && !Array.isArray(value)) {
    if (typeof value.logLevel === "string") out.logLevel = value.logLevel
    if (typeof value.keepVisibleOnFocusLoss === "boolean") out.keepVisibleOnFocusLoss = value.keepVisibleOnFocusLoss
    out.general = validGeneral(value.general, settingsMigrations[0].up({}).general)
    out.fallbacks = validFallbacks(value.fallbacks)
  }
  return out
}

if (typeof module !== "undefined") {
  module.exports = {
    settingsMigrations: settingsMigrations,
    frecencyMigrations: frecencyMigrations,
    pushSearchHistory: pushSearchHistory,
    SEARCH_HISTORY_LIMIT: SEARCH_HISTORY_LIMIT,
    documents: documents,
    configDefaults: configDefaults,
    withConfigDefaults: withConfigDefaults,
    validFallbacks: validFallbacks,
    generalFields: generalFields,
    generalTypes: generalTypes
  }
}
