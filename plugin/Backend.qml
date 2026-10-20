import QtQuick
import Quickshell
import Quickshell.Io
import OmaHost
import qs.Commons
import "core/Rpc.js" as Rpc
import "core/Paths.js" as Paths
import "core/Log.js" as Log
import "core/Schema.js" as Schema
import "core/Ranker.js" as Ranker
import "core/Frecency.js" as Frecency
import "core/RootSearch.js" as RootSearch
import "core/Providers.js" as Providers
import "core/AppsProvider.js" as AppsProvider
import "core/WebSearchProvider.js" as WebSearchProvider
import "core/ExternalProvider.js" as ExternalProvider
import "core/SettingsProvider.js" as SettingsProvider
import "core/Links.js" as Links
import "core/Results.js" as Results
import "core/Execution.js" as Execution
import "services"

// The clone's backend, in-process (SPEC §2.0). It owns the paths, the host
// config, the persisted documents, the root-search providers and the method
// registry; the launcher UI and the IPC handler both go through call().
Item {
  id: backend
  objectName: "backend"

  readonly property string version: "0.1.0"
  readonly property var paths: Paths.resolve(function(name) { return Quickshell.env(name) })
  readonly property string desktop: Quickshell.env("XDG_CURRENT_DESKTOP") || "unknown"

  // Desktop entries (sortedEntries, launch, iconSource), injected by Launcher.qml.
  property var appLibrary: null

  property var config: Schema.withConfigDefaults(null)
  property bool directoriesReady: false
  readonly property bool ready: directoriesReady && settingsStore.loaded && frecencyStore.loaded

  readonly property var registry: Rpc.createRegistry()
  // Root-search sources. Apps and web search are providers like any extension's.
  readonly property var providerRegistry: Providers.createRegistry()
  readonly property double startedAt: Date.now()
  readonly property var deps: ({ Ranker: Ranker, Frecency: Frecency })

  // Every root-search candidate, rebuilt when a provider changes.
  property var candidates: []
  property var candidatesById: ({})
  property int candidatesRevision: 0

  signal notification(string method, var data)

  // ------------------------------------------------------------- dispatch

  function call(method, data) { return Rpc.call(backend.registry, method, data) }
  function callSync(method, data) { return Rpc.callSync(backend.registry, method, data) }
  function subscribe(method, callback) { return Rpc.subscribe(backend.registry, method, callback) }

  function emit(method, data) {
    Rpc.emit(backend.registry, method, data, function(m, error) {
      backend.log("error", "rpc", "subscriber of " + m + " threw: " + error)
    })
    backend.notification(method, data)
  }

  function log(level, category, message, metadata) {
    if (!Log.shouldLog(level, backend.config.logLevel)) return
    var line = Log.format(level, category, message, metadata)
    var i = Log.levelIndex(level)
    if (i >= Log.levelIndex("error")) console.error(line)
    else if (i >= Log.levelIndex("warning")) console.warn(line)
    else if (i >= Log.levelIndex("info")) console.info(line)
    else console.log(line)
  }

  // ------------------------------------------------------------ candidates

  function appEntries() {
    return backend.appLibrary ? backend.appLibrary.sortedEntries("").map(function(row) { return row.entry }) : []
  }

  function rebuildCandidates() {
    var next = Providers.candidates(backend.providerRegistry)
    var byId = ({})
    for (var j = 0; j < next.length; j++) byId[next[j].id] = next[j]
    backend.candidates = next
    backend.candidatesById = byId
    backend.candidatesRevision++
  }

  Timer {
    id: rebuildTimer
    interval: 30
    onTriggered: backend.rebuildCandidates()
  }

  // config.yaml `general` wins over what the settings document stored.
  function effectiveGeneral() {
    return Object.assign({}, settingsStore.doc.general, backend.config.general)
  }

  function searchContext() {
    return {
      commands: settingsStore.loaded ? settingsStore.doc.commands : ({}),
      frecency: frecencyStore.loaded ? frecencyStore.doc.items : ({}),
      nowMs: Date.now(),
      sensitivity: settingsStore.loaded ? backend.effectiveGeneral().rootSearchSensitivity : "medium",
      fallbacks: function(query) { return Providers.fallbacks(backend.providerRegistry, query) },
      answers: function(query) { return Providers.answers(backend.providerRegistry, query) }
    }
  }

  function decorated(id) {
    var c = backend.candidatesById[id]
    return c ? RootSearch.decorate(c, backend.searchContext(), backend.deps) : null
  }

  // ------------------------------------------------------------- execution

  function openUrl(url) { Util.execArgv(["xdg-open", url]) }

  function copyText(text) {
    Util.execArgv(["sh", "-c", 'printf %s "$1" | xclip -selection clipboard', "x-cast", text])
  }

  // What the built-in providers need from the host.
  readonly property var services: ({
    entries: function() { return backend.appEntries() },
    launch: function(appId, title) { backend.appLibrary.launch(appId, title) },
    openUrl: function(url) { backend.openUrl(url) },
    copyText: function(text) { backend.copyText(text) },
    // config.yaml `fallbacks`, else the built-in list.
    engines: function() { return backend.config.fallbacks || WebSearchProvider.DEFAULT_ENGINES }
  })

  function registerProviders() {
    Providers.register(backend.providerRegistry, AppsProvider.createAppsProvider(backend.services))
    Providers.register(backend.providerRegistry, WebSearchProvider.createWebSearchProvider(backend.services))
    Providers.register(backend.providerRegistry, SettingsProvider.createSettingsProvider())
    // Python plugins from the host (host/plugins.py).
    JSON.parse(PluginHost.providers()).forEach(function(info) {
      Providers.register(backend.providerRegistry, ExternalProvider.createExternalProvider(PluginHost, info))
    })
  }

  // Display sessions own snapshots; ordinary searches never allocate or expire them.
  readonly property var results: Results.create(function(id) { return Providers.get(backend.providerRegistry, id) })
  readonly property var execution: Execution.create({
    resolve: function(target) {
      var resolved = target.ref ? backend.results.resolve(target.ref) : { candidate: backend.decorated(target.id), query: "" }
      var c = resolved.candidate
      if (!c || !Providers.get(backend.providerRegistry, c.provider)) throw new Error("Unknown command or provider")
      var settings = settingsStore.doc.commands[c.id]
      if (settings && settings.enabled === false) throw new Error("Command is disabled")
      return resolved
    },
    identity: function(c) { return Providers.get(backend.providerRegistry, c.provider) },
    actions: function(c) { return Providers.actionsFor(backend.providerRegistry, c) },
    perform: function(c, action, ctx) { return Providers.perform(backend.providerRegistry, c, action, ctx) },
    generic: function(c, action) { return backend.performGeneric(c, action) },
    isGeneric: function(action) { return ["favorite-add", "favorite-remove", "favorite-up", "favorite-down", "set-alias", "remove-alias", "reset-ranking", "disable"].indexOf(action) >= 0 },
    visit: function(id, query) { backend.recordVisit(id, query) }
  })

  function targetFor(data) { return data && data.ref ? { ref: data.ref } : { id: String(data && data.id || "") } }

  function searchSections(data) {
    var query = String(data && data.query || "")
    var pool = RootSearch.filterByType(backend.candidates, String(data && data.filter || ""))
    var sections = RootSearch.rootSections(pool, query, backend.searchContext(), backend.deps)
    return sections.map(function(s) {
      return { id: s.id, title: s.title, rows: s.rows.map(function(r) { return r.candidate }) }
    })
  }

  function recordVisit(id, query) {
    if (!frecencyStore.loaded) return
    frecencyStore.update(function(doc) {
      doc.items[id] = Frecency.recordVisit(doc.items[id] || null, Date.now(), query || "")
      if (query) doc.searchHistory = Schema.pushSearchHistory(doc.searchHistory, query)
    })
  }

  function updateCommand(id, mutator) {
    settingsStore.update(function(doc) {
      var current = doc.commands[id] || {}
      var next = mutator(JSON.parse(JSON.stringify(current)))
      var empty = true
      for (var k in next) if (next[k] !== null && next[k] !== undefined && next[k] !== "") empty = false
      if (empty) delete doc.commands[id]
      else doc.commands[id] = next
    })
    backend.emit("settings.commandSettingsChanged", { commandId: id })
  }

  // One action on one row. Returns what the UI should do next:
  // { close, push: {view}, toast: {style, title}, hud: "text" }.
  function performAction(data) {
    // QML var properties can expose QVariantList wrappers rather than JS arrays.
    var args = JSON.parse(JSON.stringify((data && data.arguments) || []))
    var request = { target: backend.targetFor(data), arguments: args }
    if (data && data.action !== undefined) request.action = data.action
    if (data && data.continuation) request.continuation = data.continuation
    return backend.execution.execute(request)
  }

  function performGeneric(candidate, action) {
    var id = candidate.id
    switch (action) {
      case "favorite-add":
      case "favorite-remove":
      case "favorite-up":
      case "favorite-down":
        var orders = RootSearch.reorderFavorites(settingsStore.doc.commands, id, action)
        settingsStore.update(function(doc) {
          for (var key in orders) {
            var entry = doc.commands[key] || {}
            if (orders[key] === null) delete entry.favoriteOrder
            else entry.favoriteOrder = orders[key]
            if (Object.keys(entry).length === 0) delete doc.commands[key]
            else doc.commands[key] = entry
          }
        })
        var titles = { "favorite-add": "Added to Favorites", "favorite-remove": "Removed from Favorites", "favorite-up": "Moved Up", "favorite-down": "Moved Down" }
        return { toast: { style: "success", title: titles[action] } }
      case "set-alias":
        return { push: { kind: "alias", commandId: id, title: "Alias for " + candidate.title, value: candidate.alias } }
      case "remove-alias":
        backend.updateCommand(id, function(s) { delete s.alias; return s })
        return { toast: { style: "success", title: "Alias removed" } }
      case "reset-ranking":
        frecencyStore.update(function(doc) { delete doc.items[id] })
        return { toast: { style: "success", title: "Ranking reset" } }
      case "disable":
        backend.updateCommand(id, function(s) { s.enabled = false; return s })
        return { toast: { style: "success", title: candidate.title + " disabled" } }
    }
    throw new Error("Unknown action " + action)
  }

  // ------------------------------------------------------------- services

  function registerServices() {
    Rpc.register(backend.registry, "system", {
      // Raycast's probe answers with nothing [O]; the round trip is the point.
      healthPing: function() { return null },
      healthDatabase: function() {
        var t0 = Date.now()
        JSON.stringify(settingsStore.doc)
        JSON.stringify(frecencyStore.doc)
        return {
          workMs: Date.now() - t0,
          settings: { loaded: settingsStore.loaded, readOnly: settingsStore.readOnly, error: settingsStore.lastError },
          frecency: { loaded: frecencyStore.loaded, readOnly: frecencyStore.readOnly, error: frecencyStore.lastError },
          // Kept for Phase 0 callers.
          loaded: settingsStore.loaded, readOnly: settingsStore.readOnly, error: settingsStore.lastError
        }
      },
      info: function() {
        return {
          version: backend.version,
          desktop: backend.desktop,
          ready: backend.ready,
          uptimeMs: Date.now() - backend.startedAt,
          candidates: backend.candidates.length,
          appLibrary: !!backend.appLibrary,
          methods: Rpc.methods(backend.registry)
        }
      },
      getPaths: function() { return backend.paths },
      copyText: function(data) { backend.copyText(String(data && data.text || "")); return null },
      openUrl: function(data) { backend.openUrl(String(data && data.url || "")); return null }
    })

    Rpc.register(backend.registry, "settings", {
      getGeneralSettings: function() {
        if (!settingsStore.loaded) throw new Error("settings not loaded")
        return backend.effectiveGeneral()
      },
      // Partial update; only known keys with a matching type are accepted.
      updateGeneralSettings: function(data) {
        if (!settingsStore.loaded) throw new Error("settings not loaded")
        if (settingsStore.readOnly) throw new Error("settings are read-only: " + (settingsStore.lastError || "written by a newer build"))
        var patch = data && typeof data === "object" ? data : {}
        var current = settingsStore.doc.general
        for (var key in patch) {
          if (current[key] === undefined) throw new Error("Unknown general setting " + key)
          if (typeof patch[key] !== typeof current[key]) throw new Error("Setting " + key + " must be a " + typeof current[key])
        }
        settingsStore.update(function(doc) { for (var k in patch) doc.general[k] = patch[k] })
        backend.emit("settings.generalSettingsChanged", settingsStore.doc.general)
        return settingsStore.doc.general
      },
      // Every command including disabled ones, for the settings window.
      listCommands: function() {
        var commands = settingsStore.doc.commands
        return backend.candidates.map(function(c) {
          var s = commands[c.id] || {}
          return { id: c.id, title: c.title, typeLabel: c.typeLabel || "", provider: c.provider || "",
                   enabled: s.enabled !== false, alias: s.alias || "", favorite: typeof s.favoriteOrder === "number" }
        })
      },
      listProviders: function() {
        return backend.providerRegistry.order.map(function(id) {
          return { id: id, commands: backend.candidates.filter(function(c) { return c.provider === id }).length }
        })
      },
      getAllCommandSettings: function() { return settingsStore.doc.commands },
      getCommandSettings: function(data) { return settingsStore.doc.commands[String(data && data.commandId || "")] || {} },
      // {commandId, alias?, enabled?}; null clears a field. [O name]
      updateCommandSettings: function(data) {
        var id = String(data && data.commandId || "")
        if (!backend.candidatesById[id]) throw new Error("Unknown command " + id)
        if (data.alias !== undefined && data.alias !== null) {
          var alias = String(data.alias).trim().toLowerCase()
          if (/\s/.test(alias)) throw new Error("An alias cannot contain spaces")
          var commands = settingsStore.doc.commands
          for (var other in commands) {
            if (other !== id && commands[other].alias === alias && alias) throw new Error("Alias “" + alias + "” is already used by " + ((backend.candidatesById[other] || {}).title || other))
          }
        }
        backend.updateCommand(id, function(s) {
          if (data.alias !== undefined) { if (data.alias) s.alias = String(data.alias).trim().toLowerCase(); else delete s.alias }
          if (data.enabled !== undefined) { if (data.enabled === false) s.enabled = false; else delete s.enabled }
          return s
        })
        return settingsStore.doc.commands[id] || {}
      }
    })

    Rpc.register(backend.registry, "rootSearch", {
      // {query} -> sections of plain rows.
      search: function(data) {
        var sections = backend.searchSections(data)
        return data && data.session ? backend.results.replace(data.session, sections, data.query) : sections
      },
      openSession: function() { return backend.results.open() },
      closeSession: function(data) { backend.results.close(String(data && data.session || "")); return null },
      cancelPrompt: function(data) { backend.execution.cancel(data && data.continuation); return null },
      // The root view's dropdown (Ctrl+P): [{id, title}].
      getFilters: function() { return RootSearch.typeFilters(backend.candidates, Providers.filters(backend.providerRegistry)) },
      getActions: function(data) {
        var target = backend.targetFor(data)
        var candidate = target.ref ? backend.results.resolve(target.ref).candidate : backend.decorated(target.id)
        if (!candidate) throw new Error("Unknown command " + (data && data.id))
        return RootSearch.actionsFor(candidate, backend.execution.actions(target))
      },
      performAction: function(data) { return backend.performAction(data) },
      // A raycast:// link: run the local command with the same slug, else ask for a search. [D]
      openLink: function(data) {
        var link = Links.parse(String(data && data.url || ""))
        if (!link) return { unsupported: true }
        var commands = settingsStore.doc.commands
        var pool = backend.candidates.filter(function(c) { return !(commands[c.id] && commands[c.id].enabled === false) })
        var hit = Links.resolve(pool, link)
        if (!hit) return { search: link.command.replace(/-/g, " ") }
        return backend.performAction({ id: hit.candidate.id, arguments: hit.arguments })
      },
      getSearchHistory: function() { return frecencyStore.loaded ? frecencyStore.doc.searchHistory : [] }
    })

    Rpc.register(backend.registry, "frecency", {
      visit: function(data) { backend.recordVisit(String(data.id), String(data.query || "")); return null },
      get: function(data) {
        var entry = frecencyStore.doc.items[String(data && data.id || "")]
        return entry ? { anchor: entry.anchor, openedAt: entry.openedAt, score: Frecency.score(entry.anchor, Date.now() / 1000), searchTerms: entry.searchTerms } : null
      }
    })
  }

  Component.onCompleted: {
    backend.config = Schema.withConfigDefaults(HostConfig.config)
    registerProviders()
    registerServices()
    mkdirs.running = true
  }

  onAppLibraryChanged: rebuildTimer.restart()

  Connections {
    target: backend.appLibrary
    ignoreUnknownSignals: true
    function onAppsChanged() { rebuildTimer.restart() }
  }

  Component.onDestruction: { settingsStore.flush(); frecencyStore.flush() }

  // ------------------------------------------------------------ persistence

  Process {
    id: mkdirs
    command: ["mkdir", "-p"].concat(Paths.directoriesToCreate(backend.paths))
    onExited: function(exitCode) {
      if (exitCode !== 0) backend.log("error", "paths", "could not create data directories", { exitCode: exitCode })
      backend.directoriesReady = true
    }
  }

  JsonStore {
    id: settingsStore
    ready: backend.directoriesReady
    path: backend.paths.db + "/" + Schema.documents.settings.file
    migrations: Schema.documents.settings.migrations
    onMessage: function(level, text, metadata) { backend.log(level, "store", text, metadata) }
  }

  JsonStore {
    id: frecencyStore
    ready: backend.directoriesReady
    path: backend.paths.db + "/" + Schema.documents.frecency.file
    migrations: Schema.documents.frecency.migrations
    onMessage: function(level, text, metadata) { backend.log(level, "store", text, metadata) }
  }

  // Bumped whenever ranking inputs change, so views re-query.
  readonly property int dataRevision: candidatesRevision + (settingsStore.loaded ? 1 : 0) + (frecencyStore.loaded ? 1 : 0)
  property int storeRevision: 0
  Connections { target: settingsStore; function onChanged() { backend.storeRevision++ } }
  Connections { target: frecencyStore; function onChanged() { backend.storeRevision++ } }

  Connections {
    target: PluginHost
    function onChanged() { rebuildTimer.restart() }
  }

  // config.yaml is parsed by the host, which re-sends it on every save.
  Connections {
    target: HostConfig
    function onConfigChanged() {
      backend.config = Schema.withConfigDefaults(HostConfig.config)
      backend.storeRevision++
    }
  }
}
