// Provider: desktop entries (applications). Built in, registered like any plugin.
//
// services: { entries() -> [{id, name, genericName, keywords, icon}],
//             launch(appId, title), copyText(text) }

function appCandidate(entry) {
  var desktopId = String(entry.id || "")
  var keywords = []
  if (entry.genericName) keywords.push(String(entry.genericName))
  try {
    if (entry.keywords && entry.keywords.length) for (var i = 0; i < entry.keywords.length; i++) if (entry.keywords[i]) keywords.push(String(entry.keywords[i]))
  } catch (e) {}
  return {
    id: "app:" + desktopId,
    type: "application",
    title: String(entry.name || desktopId),
    subtitle: "",
    keywords: keywords,
    bundleId: desktopId,               // matched only for queries with "." [O]
    typeLabel: "Application",
    appId: desktopId,
    iconName: String(entry.icon || ""),
    rootSearch: { when: "always" }
  }
}

function createAppsProvider(services) {
  return {
    id: "apps",

    candidates: function() {
      return services.entries().filter(function(e) { return e && e.id }).map(appCandidate)
    },

    actionsFor: function(candidate) {
      return [
        { id: "open", title: "Open Application", icon: "\uf35d" },
        { id: "copy-id", title: "Copy Desktop ID", shortcut: "Ctrl Shift C", section: "copy", icon: "\uf0c5" }
      ]
    },

    perform: function(candidate, actionId) {
      if (actionId === "open") {
        services.launch(candidate.appId, candidate.title)
        return { close: true, visit: true }
      }
      if (actionId === "copy-id") {
        services.copyText(candidate.appId + ".desktop")
        return { close: true, hud: "Copied to Clipboard" }
      }
    }
  }
}

if (typeof module !== "undefined") {
  module.exports = { appCandidate: appCandidate, createAppsProvider: createAppsProvider }
}
