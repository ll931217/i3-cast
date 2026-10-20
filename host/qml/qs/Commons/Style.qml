pragma Singleton
import QtQuick
import OmaHost

// Sizes and fonts come from ~/.config/x-cast/theme.yaml; a missing or malformed value keeps its default.
QtObject {
  readonly property var theme: HostConfig.theme
  readonly property var fonts: theme.font || ({})

  function number(v, fallback) { return typeof v === "number" && v > 0 ? v : fallback }
  function text(v, fallback) { return typeof v === "string" && v.length > 0 ? v : fallback }

  readonly property int cornerRadius: number(theme.cornerRadius, 8)
  readonly property int gapsOut: number(theme.gap, 10)
  function space(n) { return n }
  readonly property QtObject spacing: QtObject { readonly property int hairline: 1 }
  readonly property QtObject font: QtObject {
    readonly property string menuFamily: text(fonts.family, "Sans")
    readonly property string iconFamily: text(fonts.iconFamily, "JetBrainsMono Nerd Font")
    readonly property int caption: number(fonts.caption, 12)
    readonly property int bodySmall: number(fonts.bodySmall, 13)
    readonly property int body: number(fonts.body, 14)
    readonly property int title: number(fonts.title, 16)
    readonly property int heading: number(fonts.heading, 20)
  }
}
