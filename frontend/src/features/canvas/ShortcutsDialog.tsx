import { t, type TranslationKey } from "../../i18n/es-CL";
import { Dialog } from "../../ui";

const ROWS: readonly { keys: string; labelKey: TranslationKey }[] = [
  { keys: "V", labelKey: "shortcut.toolSelect" },
  { keys: "|", labelKey: "shortcut.toolSplitV" },
  { keys: "-", labelKey: "shortcut.toolSplitH" },
  { keys: "A", labelKey: "shortcut.toolOpening" },
  { keys: "Vd", labelKey: "shortcut.toolGlazing" },
  { keys: "M", labelKey: "shortcut.toolMeasure" },
  { keys: "B", labelKey: "shortcut.starterLibrary" },
  { keys: "Enter", labelKey: "shortcut.descend" },
  { keys: "Esc", labelKey: "shortcut.ascend" },
  { keys: "← → ↑ ↓", labelKey: "shortcut.nudge" },
  { keys: "Shift + ← → ↑ ↓", labelKey: "shortcut.nudgeBig" },
  { keys: "Espacio + arrastre", labelKey: "shortcut.pan" },
  { keys: "Rueda", labelKey: "shortcut.zoom" },
  { keys: "F", labelKey: "shortcut.fit" },
  { keys: "Supr", labelKey: "shortcut.delete" },
  { keys: "Ctrl + Z", labelKey: "shortcut.undo" },
  { keys: "Ctrl + Mayús + Z", labelKey: "shortcut.redo" },
  { keys: "Ctrl + S", labelKey: "shortcut.save" },
  { keys: "Ctrl + K", labelKey: "shortcut.palette" },
  { keys: "Doble clic en vano", labelKey: "shortcut.openingPicker" },
  { keys: "?", labelKey: "shortcut.shortcuts" },
];

/** `?` opens the shortcuts sheet — the full modal contract of the editor
 * in one glance (single-key entries only work outside a field). */
export function ShortcutsDialog({ onClose }: { onClose(): void }): JSX.Element {
  return (
    <Dialog title={t("assembly.shortcutsTitle")} onClose={onClose} width="m">
      <table className="shortcuts-table">
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.keys}>
              <td className="shortcuts-table__keys">
                <kbd>{row.keys}</kbd>
              </td>
              <td>{t(row.labelKey)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Dialog>
  );
}
