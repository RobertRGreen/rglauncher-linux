#!/usr/bin/env python3
"""Build the data-only RGLauncher Aether themes and deterministic local VSIX.

No extension runtime code, npm, publishing, user-profile reads or editor launch.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DEFAULT_ICON_SOURCE = Path(__file__).resolve().parents[1] / "assets/icons"
NIGHT = {
    "canvas": "#090e18", "editor": "#0d1421", "surface": "#131c2d", "raised": "#1c2940",
    "text": "#edf4ff", "secondary": "#a3b3c9", "line": "#33445f", "control": "#667e9f",
    "cyan": "#73e4f2", "violet": "#bba6ff", "green": "#78deb0", "amber": "#f2c77d",
    "red": "#ff8f9f", "blue": "#9bc4ff", "selection": "#234557", "selectionInactive": "#24344c",
    "button": "#73e4f2", "onButton": "#090e18", "buttonHover": "#a2edf6",
    "comment": "#a3b3c9", "property": "#b7d0ef", "parameter": "#d2ddee", "constant": "#f2c77d",
    "infoPlane": "#12303e", "warningPlane": "#362b1c", "errorPlane": "#3d222e",
    "debugPlane": "#2c2741", "addPlane": "#14382e", "deletePlane": "#3d222e",
}
DAY = {
    "canvas": "#edf3f8", "editor": "#fcfdff", "surface": "#f5f8fc", "raised": "#e5edf5",
    "text": "#17263a", "secondary": "#4f6178", "line": "#cad6e4", "control": "#667994",
    "cyan": "#006979", "violet": "#6447a0", "green": "#246b4f", "amber": "#855700",
    "red": "#aa2e48", "blue": "#235a9b", "selection": "#c6e7ef", "selectionInactive": "#dce5f0",
    "button": "#006979", "onButton": "#ffffff", "buttonHover": "#005665",
    "comment": "#4f6178", "property": "#284f7f", "parameter": "#354c68", "constant": "#855700",
    "infoPlane": "#dceff4", "warningPlane": "#f4e8cc", "errorPlane": "#f5dfe5",
    "debugPlane": "#e8e1f3", "addPlane": "#ddf0e6", "deletePlane": "#f5dfe5",
}


def composite(foreground, background):
    """Resolve a hex sRGB overlay over its declared working plane."""
    if len(foreground) == 7:
        return foreground
    alpha = int(foreground[7:9], 16) / 255
    fg = [int(foreground[i:i + 2], 16) for i in (1, 3, 5)]
    bg = [int(background[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a * alpha + b * (1 - alpha)):02x}" for a, b in zip(fg, bg))


def color_theme(edition):
    p = copy.deepcopy(DAY if edition == "day" else NIGHT)
    opaque = edition == "opaque"
    colors = {}

    def put(role, names):
        color = p.get(role, role)
        for name in names.split():
            colors[name] = color

    def overlay(role, alpha, names, background="editor"):
        value = p[role] + alpha
        put(composite(value, p[background]) if opaque else value, names)

    put("text", "foreground editor.foreground input.foreground dropdown.foreground list.activeSelectionForeground list.inactiveSelectionForeground list.focusForeground list.hoverForeground quickInput.foreground quickInputList.focusForeground menu.foreground panelTitle.activeForeground titleBar.activeForeground sideBar.foreground sideBarSectionHeader.foreground notificationCenterHeader.foreground notifications.foreground terminal.foreground settings.textInputForeground settings.numberInputForeground settings.dropdownForeground settings.checkboxForeground peekViewResult.fileForeground peekViewResult.lineForeground debugConsole.sourceForeground")
    put("secondary", "descriptionForeground disabledForeground input.placeholderForeground titleBar.inactiveForeground tab.inactiveForeground tab.unfocusedInactiveForeground panelTitle.inactiveForeground activityBar.inactiveForeground activityBarTop.inactiveForeground breadcrumb.foreground editorCodeLens.foreground editorLineNumber.foreground editorGhostText.foreground editorInlayHint.foreground editorInlayHint.typeForeground editorInlayHint.parameterForeground terminal.initialHintForeground settings.headerForeground notificationsInfoIcon.foreground gitDecoration.ignoredResourceForeground gitDecoration.stageDeletedResourceForeground list.deemphasizedForeground pickerGroup.foreground")
    put("canvas", "activityBar.background activityBarTop.background sideBar.background titleBar.activeBackground titleBar.inactiveBackground statusBar.background statusBar.noFolderBackground editorGroupHeader.tabsBackground panel.background terminal.background notebook.editorBackground debugToolBar.background menu.background  notifications.background notificationCenterHeader.background banner.background editorWidget.background peekViewTitle.background peekViewResult.background breadcrumb.background commandCenter.background")
    put("editor", "editor.background tab.activeBackground tab.unfocusedActiveBackground notebook.cellEditorBackground mergeEditor.conflict.input1.background mergeEditor.conflict.input2.background peekViewEditor.background")
    put("surface", "input.background dropdown.background dropdown.listBackground settings.textInputBackground settings.numberInputBackground settings.dropdownBackground settings.checkboxBackground button.secondaryBackground keybindingLabel.background toolbar.hoverBackground welcomePage.tileBackground  editorGutter.background notebook.outputContainerBackgroundColor editorStickyScroll.background activityBar.activeBackground sideBarSectionHeader.background editorHoverWidget.background quickInput.background quickInputTitle.background debugExceptionWidget.background editorSuggestWidget.background badge.background progressBar.background extensionButton.separator")
    put("raised", "tab.inactiveBackground tab.hoverBackground tab.unfocusedHoverBackground list.hoverBackground settings.rowHoverBackground notebook.cellHoverBackground toolbar.activeBackground editorInlayHint.background editorInlayHint.typeBackground editorInlayHint.parameterBackground inputOption.hoverBackground actionBar.toggledBackground menu.selectionBackground editorSuggestWidget.selectedBackground")
    put("line", "activityBar.border  sideBar.border sideBarSectionHeader.border panel.border titleBar.border statusBar.border tab.border tab.lastPinnedBorder editorGroup.border editorGroupHeader.border editorWidget.border editorHoverWidget.border notebook.cellBorderColor notebook.outputContainerBorderColor notebook.cellToolbarSeparator settings.headerBorder settings.sashBorder menu.border commandCenter.border editorRuler.foreground editorIndentGuide.background1 editorIndentGuide.background2 editorIndentGuide.background3 editorIndentGuide.background4 editorIndentGuide.background5 editorIndentGuide.background6 editorWhitespace.foreground editorStickyScroll.border terminal.border diffEditor.border widget.border notificationToast.border notifications.border ")
    put("control", "input.border dropdown.border settings.textInputBorder settings.numberInputBorder settings.dropdownBorder settings.dropdownListBorder settings.checkboxBorder button.secondaryBorder checkbox.border checkbox.selectBorder editorSuggestWidget.border keybindingLabel.border keybindingLabel.bottomBorder notebook.inactiveFocusedCellBorder notebook.inactiveSelectedCellBorder peekView.border")
    put("surface", "keybindingTable.headerBackground")
    put("violet", "focusBorder contrastActiveBorder activityBar.activeFocusBorder settings.focusedRowBorder editorSuggestWidget.focusHighlightForeground editorWidget.resizeBorder commandCenter.activeBorder commandCenter.activeForeground textLink.activeForeground gitDecoration.modifiedResourceForeground gitDecoration.stageModifiedResourceForeground debugIcon.breakpointCurrentStackframeForeground")
    put("cyan", "textLink.foreground activityBar.foreground activityBar.activeBorder activityBarTop.foreground activityBarTop.activeBorder panelTitle.activeBorder tab.activeBorderTop tab.selectedBorderTop tab.hoverBorder tab.dragAndDropBorder list.highlightForeground list.focusHighlightForeground list.activeSelectionIconForeground editorCursor.foreground editorLineNumber.activeForeground editorSuggestWidget.highlightForeground editorSuggestWidget.selectedIconForeground editorSuggestWidget.selectedForeground terminalCursor.foreground terminal.tab.activeBorder breadcrumb.focusForeground breadcrumb.activeSelectionForeground pickerGroup.foreground quickInputList.focusIconForeground activityBar.dropBorder activityBarTop.dropBorder progressBar.background notebook.focusedCellBorder notebook.cellInsertionIndicator notebook.selectedCellBorder notebook.focusedEditorBorder settings.modifiedItemIndicator settings.settingsHeaderHoverForeground ports.iconRunningProcessForeground icon.foreground commandCenter.foreground debugConsole.infoForeground extensionIcon.verifiedForeground")
    put("button", "button.background extensionButton.prominentBackground extensionButton.background")
    put("onButton", "button.foreground extensionButton.prominentForeground extensionButton.foreground badge.foreground activityBarBadge.foreground activityWarningBadge.foreground activityErrorBadge.foreground")
    put("buttonHover", "button.hoverBackground extensionButton.prominentHoverBackground extensionButton.hoverBackground")
    put("text", "button.secondaryForeground keybindingLabel.foreground menu.selectionForeground statusBar.foreground statusBar.noFolderForeground statusBar.debuggingForeground statusBarItem.remoteForeground")
    put("cyan", "button.border inputOption.activeBorder inputOption.activeForeground checkbox.foreground  activityBarBadge.background list.dropBetweenBackground menu.selectionBorder ")
    put("selection", "selection.background editor.selectionBackground terminal.selectionBackground list.activeSelectionBackground list.focusBackground quickInputList.focusBackground inputOption.activeBackground tab.selectedBackground notebook.selectedCellBackground notebook.focusedCellBackground")
    put("selectionInactive", "editor.inactiveSelectionBackground terminal.inactiveSelectionBackground list.inactiveSelectionBackground list.inactiveFocusBackground")
    put("text", "terminal.selectionForeground editor.selectionForeground")
    put("debugPlane", "statusBar.debuggingBackground statusBarItem.remoteBackground statusBarItem.prominentBackground debugExceptionWidget.background")
    put("warningPlane", "inputValidation.warningBackground statusBarItem.warningBackground banner.background editorWarning.background")
    put("errorPlane", "inputValidation.errorBackground statusBarItem.errorBackground editorError.background")
    put("infoPlane", "inputValidation.infoBackground editorInfo.background")
    put("amber", "editorWarning.foreground editorWarning.border inputValidation.warningForeground inputValidation.warningBorder statusBarItem.warningForeground notificationsWarningIcon.foreground debugConsole.warningForeground gitDecoration.conflictingResourceForeground list.warningForeground activityWarningBadge.background problemsWarningIcon.foreground testing.iconQueued debugIcon.pauseForeground debugIcon.breakpointStackframeForeground")
    put("red", "errorForeground editorError.foreground editorError.border inputValidation.errorForeground inputValidation.errorBorder statusBarItem.errorForeground notificationsErrorIcon.foreground debugConsole.errorForeground gitDecoration.deletedResourceForeground gitDecoration.stageDeletedResourceForeground list.errorForeground activityErrorBadge.background problemsErrorIcon.foreground testing.iconFailed debugIcon.breakpointForeground debugIcon.stopForeground debugIcon.disconnectForeground")
    put("cyan", "editorInfo.foreground editorInfo.border inputValidation.infoForeground inputValidation.infoBorder problemsInfoIcon.foreground testing.iconUnset debugIcon.continueForeground debugIcon.stepOverForeground debugIcon.stepIntoForeground debugIcon.stepOutForeground debugIcon.stepBackForeground")
    put("green", "gitDecoration.addedResourceForeground  gitDecoration.untrackedResourceForeground testing.iconPassed debugIcon.startForeground debugIcon.restartForeground editorGutter.addedBackground editorOverviewRuler.addedForeground")
    put("violet", "editorGutter.modifiedBackground editorOverviewRuler.modifiedForeground debugTokenExpression.name debugTokenExpression.type")
    put("red", "editorGutter.deletedBackground editorOverviewRuler.deletedForeground editorOverviewRuler.errorForeground debugIcon.breakpointUnverifiedForeground")
    put("amber", "editorOverviewRuler.warningForeground debugTokenExpression.number debugTokenExpression.boolean")
    put("green", "debugTokenExpression.string")
    put("text", "debugTokenExpression.value  ")
    put("line", "debugIcon.breakpointDisabledForeground editorBracketMatch.background editorOverviewRuler.border editorUnnecessaryCode.border")
    put("cyan", "editorBracketMatch.border editorBracketHighlight.foreground1 editorBracketHighlight.foreground4")
    put("violet", "editorBracketHighlight.foreground2 editorBracketHighlight.foreground5")
    put("amber", "editorBracketHighlight.foreground3 editorBracketHighlight.foreground6")
    put("red", "")
    put("secondary", "editorUnnecessaryCode.opacity")
    # editorUnnecessaryCode.opacity is a color-encoded opacity, not a text role.
    colors.pop("editorUnnecessaryCode.opacity", None)
    put("raised", "editor.lineHighlightBackground editor.inactiveLineHighlightBackground settings.focusedRowBackground peekViewEditor.matchHighlightBackground")
    put("line", "editor.lineHighlightBorder editorIndentGuide.activeBackground1 editorIndentGuide.activeBackground2 editorIndentGuide.activeBackground3 editorIndentGuide.activeBackground4 editorIndentGuide.activeBackground5 editorIndentGuide.activeBackground6")
    put("control", "editorIndentGuide.activeBackground1")
    overlay("cyan", "25", "editor.selectionHighlightBackground editor.wordHighlightStrongBackground editor.linkedEditingBackground terminal.findMatchHighlightBackground notebook.symbolHighlightBackground editor.rangeHighlightBackground")
    overlay("violet", "1f", "editor.wordHighlightBackground editor.hoverHighlightBackground editor.foldBackground editor.findRangeHighlightBackground")
    put("cyan", "editor.selectionHighlightBorder editor.wordHighlightStrongBorder editor.findMatchBorder terminal.findMatchBorder")
    put("violet", "editor.wordHighlightBorder editor.findRangeHighlightBorder ")
    put("warningPlane", "editor.findMatchBackground terminal.findMatchBackground")
    put("text", "editor.findMatchForeground")
    overlay("amber", "28", "editor.findMatchHighlightBackground")
    put("amber", "editor.findMatchHighlightBorder terminal.findMatchHighlightBorder")
    put("addPlane", "diffEditor.insertedLineBackground diffEditor.insertedTextBackground diffEditorGutter.insertedLineBackground merge.currentHeaderBackground merge.currentContentBackground mergeEditor.conflict.handledFocused.border")
    put("deletePlane", "diffEditor.removedLineBackground diffEditor.removedTextBackground diffEditorGutter.removedLineBackground merge.incomingHeaderBackground merge.incomingContentBackground")
    put("green", "diffEditor.insertedTextBorder diffEditorOverview.insertedForeground")
    put("red", "diffEditor.removedTextBorder diffEditorOverview.removedForeground")
    put("surface", "diffEditor.unchangedCodeBackground diffEditor.unchangedRegionBackground")
    put("secondary", "diffEditor.unchangedRegionForeground")
    put("violet", "diffEditor.move.border diffEditor.moveActive.border")
    put("line", "diffEditor.diagonalFill")
    put("errorPlane", "mergeEditor.conflict.unhandledUnfocused.border")
    put("amber", "mergeEditor.conflict.unhandledFocused.border mergeEditor.conflictingLines.background")
    put("control", "merge.border mergeEditor.conflict.handledUnfocused.border")
    put("text", "notebook.selectedCellBorder settings.dropdownForeground")
    put("cyan", "notebook.selectedCellBorder")
    put("line", "notebookStatusErrorIcon.foreground")
    put("red", "notebookStatusErrorIcon.foreground")
    put("green", "notebookStatusSuccessIcon.foreground")
    put("violet", "notebookStatusRunningIcon.foreground")
    put("line", "chart.axis chart.guide charts.lines")
    put("text", "charts.foreground")
    put("blue", "charts.blue")
    put("green", "charts.green")
    put("red", "charts.red")
    put("amber", "charts.yellow charts.orange")
    put("violet", "charts.purple")
    put("surface", "textCodeBlock.background textBlockQuote.background textPreformat.background")
    put("cyan", "textBlockQuote.border textPreformat.foreground")
    put("line", "textSeparator.foreground welcomePage.tileBorder")
    put("violet", "welcomePage.progress.foreground")
    put("raised", "welcomePage.tileHoverBackground")
    put("surface", "welcomePage.progress.background")
    put("control", "scrollbarSlider.background")
    put("secondary", "scrollbarSlider.hoverBackground")
    put("cyan", "scrollbarSlider.activeBackground")
    overlay("canvas", "90", "scrollbar.shadow widget.shadow editorStickyScroll.shadow diffEditor.unchangedRegionShadow", "canvas")
    put("line", " ")
    overlay("secondary", "66", "minimapSlider.background")
    overlay("secondary", "88", "minimapSlider.hoverBackground")
    overlay("cyan", "77", "minimapSlider.activeBackground")
    put("green", "minimapGutter.addedBackground")
    put("violet", "minimapGutter.modifiedBackground")
    put("red", "minimapGutter.deletedBackground minimap.errorHighlight")
    put("amber", "minimap.warningHighlight minimap.findMatchHighlight")
    put("cyan", "minimap.selectionHighlight editorOverviewRuler.findMatchForeground")
    put("raised", "editor.snippetTabstopHighlightBackground")
    put("control", "editor.snippetTabstopHighlightBorder editor.snippetFinalTabstopHighlightBorder")
    put("surface", "editor.snippetFinalTabstopHighlightBackground")
    # Chat and inline edit remain subordinate to the editor work plane.
    put("surface", "inlineChat.background inlineChatInput.background chat.requestBackground chat.slashCommandBackground ")
    put("control", "inlineChat.border inlineChatInput.border chat.requestBorder  ")
    put("violet", "inlineChatInput.focusBorder")
    put("text", "inlineChatInput.placeholderForeground  chat.slashCommandForeground")
    put("secondary", "")
    # Keep black/white meaning for TUI/background uses; don't turn ANSI black
    # into a light secondary-text token merely to improve one foreground pair.
    ansi = {"Black": "#090e18", "Red": p["red"], "Green": p["green"], "Yellow": p["amber"],
            "Blue": p["blue"], "Magenta": p["violet"], "Cyan": p["cyan"], "White": "#edf4ff"}
    for suffix, value in ansi.items():
        colors["terminal.ansi" + suffix] = value
        colors["terminal.ansiBright" + suffix] = value
    colors["terminal.ansiBrightBlack"] = p["secondary"]
    put("canvas", "terminalCursor.background")

    syntax = [
        ("Reading and punctuation", ["punctuation", "variable", "meta.embedded"], "text", ""),
        ("Comments", ["comment", "punctuation.definition.comment"], "comment", ""),
        ("Keywords and storage", ["keyword", "storage.type", "storage.modifier"], "violet", ""),
        ("Strings and inline prose", ["string", "markup.inline.raw", "markup.raw.block"], "green", ""),
        ("Numbers and constants", ["constant.numeric", "constant.language", "constant.character", "variable.other.constant"], "constant", ""),
        ("Functions and methods", ["entity.name.function", "support.function"], "cyan", ""),
        ("Types and namespaces", ["entity.name.type", "entity.name.namespace", "support.type", "support.class"], "amber", ""),
        ("Parameters", ["variable.parameter"], "parameter", ""),
        ("Properties and attributes", ["variable.other.property", "entity.other.attribute-name", "support.type.property-name"], "property", ""),
        ("Operators and separators", ["keyword.operator", "punctuation.separator", "punctuation.accessor"], "secondary", ""),
        ("Tags and selectors", ["entity.name.tag", "entity.other.attribute-name.class.css", "entity.other.attribute-name.id.css"], "cyan", ""),
        ("Escapes and regular expressions", ["constant.character.escape", "string.regexp"], "amber", ""),
        ("Markdown headings", ["markup.heading", "entity.name.section"], "violet", "bold"),
        ("Markdown strong", ["markup.bold"], "text", "bold"),
        ("Markdown emphasis", ["markup.italic"], "text", "italic"),
        ("Markdown links", ["markup.underline.link"], "cyan", "underline"),
        ("Added and changed text", ["markup.inserted"], "green", ""),
        ("Deleted text", ["markup.deleted"], "red", ""),
        ("Invalid token", ["invalid", "invalid.illegal"], "red", "underline"),
        ("Deprecated token", ["invalid.deprecated"], "secondary", "strikethrough"),
    ]
    semantic = {role: p[color] for role, color in {
        "namespace": "amber", "type": "amber", "class": "amber", "enum": "amber", "interface": "amber",
        "struct": "amber", "typeParameter": "amber", "parameter": "parameter", "variable": "text",
        "property": "property", "enumMember": "constant", "event": "cyan", "function": "cyan",
        "method": "cyan", "macro": "violet", "keyword": "violet", "modifier": "violet",
        "comment": "comment", "string": "green", "number": "constant", "regexp": "amber",
        "operator": "secondary", "decorator": "violet", "variable.readonly": "constant",
        "property.readonly": "constant", "variable.defaultLibrary": "blue",
    }.items()}
    semantic.update({"function.declaration": {"foreground": p["cyan"], "bold": True},
                     "type.declaration": {"foreground": p["amber"], "bold": True},
                     "*.deprecated": {"foreground": p["secondary"], "italic": True}})
    put("green", "mergeEditor.conflict.handledFocused.border")
    put("control", "mergeEditor.conflict.unhandledUnfocused.border")
    put("warningPlane", "mergeEditor.conflictingLines.background")
    put("violet", "notebook.focusedCellBorder notebook.focusedEditorBorder list.focusOutline")
    put("control", "list.inactiveFocusOutline")
    return {"$schema": "vscode://schemas/color-theme", "name": "RGLauncher Aether " + edition.title(),
            "type": "light" if edition == "day" else "dark", "semanticHighlighting": True,
            "colors": dict(sorted(colors.items())),
            "tokenColors": [{"name": name, "scope": scopes, "settings": {"foreground": p[role], "fontStyle": style}}
                            for name, scopes, role, style in syntax],
            "semanticTokenColors": semantic}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icons-source", type=Path, default=DEFAULT_ICON_SOURCE)
    parser.add_argument("--themes-only", action="store_true")
    args = parser.parse_args()
    for edition in ("night", "opaque", "day"):
        write_json(ROOT / "themes" / ("aether-" + edition + ".json"), color_theme(edition))
    if args.themes_only:
        return
    from file_icons import build_icons
    build_icons(ROOT, args.icons_source)
    shutil.copy2(PROJECT / "LICENSE", ROOT / "LICENSE")
    from vsix import build_vsix
    path = build_vsix(ROOT)
    print(path)


if __name__ == "__main__":
    main()
