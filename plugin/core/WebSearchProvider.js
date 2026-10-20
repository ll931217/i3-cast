// Provider: "Use <query> with…" web searches. Built in, registered like any plugin.
//
// services: { openUrl(url), engines() -> [{title, url}] }   url contains {query}

// Default engines, in order [O names, D URLs]. config.yaml `fallbacks` replaces them.
var DEFAULT_ENGINES = [
  { title: "Search Google", url: "https://www.google.com/search?q={query}" },
  { title: "Search DuckDuckGo", url: "https://duckduckgo.com/?q={query}" }
]

function searchUrl(engine, query) {
  return String(engine.url || "").replace("{query}", encodeURIComponent(String(query || "").trim()))
}

function createWebSearchProvider(services) {
  return {
    id: "web-search",

    candidates: function() { return [] },

    fallbacks: function(query) {
      return services.engines().map(function(engine, i) {
        return {
          id: "fallback:" + i, type: "command", title: engine.title, subtitle: query,
          typeLabel: "Fallback", glyph: "", url: engine.url, rootSearch: { when: "searching" }
        }
      })
    },

    actionsFor: function(candidate) { return [{ id: "open", title: candidate.title, icon: "\uf002" }] },

    perform: function(candidate, actionId, ctx) {
      if (actionId !== "open") return undefined
      services.openUrl(searchUrl(candidate, ctx.query))
      return { close: true }
    }
  }
}

if (typeof module !== "undefined") {
  module.exports = { DEFAULT_ENGINES: DEFAULT_ENGINES, searchUrl: searchUrl, createWebSearchProvider: createWebSearchProvider }
}
