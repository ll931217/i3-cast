// Provider: the built-in "x-cast Settings" command. Opens the settings window.

function createSettingsProvider() {
  return {
    id: "x-cast",

    candidates: function() {
      return [{
        id: "x-cast:settings", type: "command", title: "x-cast Settings", subtitle: "x-cast",
        typeLabel: "Command", glyph: "", keywords: ["preferences", "options", "config"],
        rootSearch: { when: "always" }
      }]
    },

    actionsFor: function() { return [{ id: "open", title: "Open Settings", icon: "" }] },

    perform: function(candidate, actionId) {
      if (actionId !== "open") return undefined
      return { close: true, settings: true, visit: true }
    }
  }
}

if (typeof module !== "undefined") module.exports = { createSettingsProvider: createSettingsProvider }
