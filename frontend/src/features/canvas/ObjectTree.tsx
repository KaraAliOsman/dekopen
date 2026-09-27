import { useState, type JSX } from "react";

import { t } from "../../i18n/es-CL";
import type { TreeNode } from "./objectTree";

/** Does any descendant row own the current selection? Used to mark the
 * disclosure path — "contains the selection" is a rail accent, never the
 * selection band itself. */
function subtreeContainsSelection(node: TreeNode, selection: string | null): boolean {
  if (selection === null) return false;
  return node.children.some(
    (child) => child.selectId === selection || subtreeContainsSelection(child, selection),
  );
}

function TreeRow({
  node,
  depth,
  selection,
  onSelect,
  onContextMenu,
}: {
  node: TreeNode;
  depth: number;
  selection: string | null;
  onSelect(selectId: string): void;
  onContextMenu?(selectId: string, pos: { x: number; y: number }): void;
}): JSX.Element {
  const [open, setOpen] = useState(true);
  const selected = node.selectId !== null && node.selectId === selection;
  const expandable = node.children.length > 0;
  const inPath = !selected && subtreeContainsSelection(node, selection);
  return (
    <li role="treeitem" aria-expanded={expandable ? open : undefined} aria-selected={selected}>
      <div
        className={`tree-row tree-row--${node.kind}${selected ? " is-selected" : ""}${inPath ? " in-path" : ""}`}
        style={{ paddingLeft: `${6 + depth * 14}px` }}
      >
        {expandable ? (
          <button
            type="button"
            className="tree-disclosure"
            aria-label={`${open ? t("assembly.treeCollapse") : t("assembly.treeExpand")} ${node.label}`}
            onClick={() => setOpen((value) => !value)}
          >
            <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
              <path d={open ? "M1 2.5h6L4 6z" : "M2.5 1l3.5 3-3.5 3z"} fill="currentColor" />
            </svg>
          </button>
        ) : (
          <span className="tree-disclosure tree-disclosure--leaf" />
        )}
        <button
          type="button"
          className={`tree-label${node.selectId === null ? " is-static" : ""}`}
          aria-label={node.ariaLabel}
          onClick={() => {
            if (node.selectId !== null) onSelect(node.selectId);
          }}
          onContextMenu={(event) => {
            if (node.selectId === null || !onContextMenu) return;
            event.preventDefault();
            onContextMenu(node.selectId, { x: event.clientX, y: event.clientY });
          }}
          onKeyDown={(event) => {
            // Same keyboard menu trigger as the canvas (ContextMenu/Shift+F10),
            // anchored on the row so the object under it is unambiguous.
            if (node.selectId === null || !onContextMenu) return;
            if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
            event.preventDefault();
            const rect = event.currentTarget.getBoundingClientRect();
            onContextMenu(node.selectId, {
              x: Math.round(rect.left + rect.width / 2),
              y: Math.round(rect.top + rect.height / 2),
            });
          }}
        >
          <span className="tree-label__text">{node.label}</span>
          {node.detail && <span className="tree-label__detail">{node.detail}</span>}
          {node.severity && (
            <span
              className={`tree-severity tree-severity--${node.severity}`}
              aria-label={node.severity}
            />
          )}
        </button>
      </div>
      {expandable && open && (
        <ul role="group" className="tree-children">
          {node.children.map((child) => (
            <TreeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selection={selection}
              onSelect={onSelect}
              onContextMenu={onContextMenu}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ObjectTree({
  root,
  selection,
  onSelect,
  onContextMenu,
  title,
}: {
  root: TreeNode;
  selection: string | null;
  onSelect(selectId: string): void;
  onContextMenu?(selectId: string, pos: { x: number; y: number }): void;
  title: string;
}): JSX.Element {
  return (
    <nav className="object-tree" aria-label={title}>
      <h3 className="object-tree__title">{title}</h3>
      <ul role="tree" className="tree-root">
        {root.children.map((node) => (
          <TreeRow
            key={node.id}
            node={node}
            depth={0}
            selection={selection}
            onSelect={onSelect}
            onContextMenu={onContextMenu}
          />
        ))}
      </ul>
    </nav>
  );
}
