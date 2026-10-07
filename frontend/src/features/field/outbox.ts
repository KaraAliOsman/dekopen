import { apiMutator, ApiError } from "../../api/apiMutator";

/** Cola offline de terreno (P23): cada gesto del instalador lleva su
 * ``operation_key`` — el reintento desde la cola es una sola aplicación en
 * el servidor (idempotencia por clave), así el sync nunca duplica. */
export type OutboxEntry = {
  operation_key: string;
  path: string;
  method: "POST" | "PUT";
  body: Record<string, unknown>;
  label: string;
  queued_at: string;
};

const PREFIX = "dekopen.field.outbox.";

function storageKey(orgId: string): string {
  return `${PREFIX}${orgId}`;
}

export function outboxList(orgId: string): OutboxEntry[] {
  try {
    const raw = window.localStorage.getItem(storageKey(orgId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as OutboxEntry[]) : [];
  } catch {
    return [];
  }
}

function outboxSave(orgId: string, entries: OutboxEntry[]): void {
  window.localStorage.setItem(storageKey(orgId), JSON.stringify(entries));
}

export function outboxEnqueue(
  orgId: string,
  entry: Omit<OutboxEntry, "operation_key" | "queued_at">,
): OutboxEntry {
  const operationKey = crypto.randomUUID();
  const queued: OutboxEntry = {
    ...entry,
    body: { ...entry.body, operation_key: operationKey },
    operation_key: operationKey,
    queued_at: new Date().toISOString(),
  };
  outboxSave(orgId, [...outboxList(orgId), queued]);
  return queued;
}

/** Replays the queue in order. A 2xx (including a server-side ``replayed``
 * echo) removes the entry exactly once; a contract error drops it (the
 * server already refused it — repeating changes nothing); a network or 5xx
 * failure keeps it for the next sync. Returns how many ops synced. */
export async function outboxFlush(orgId: string): Promise<{
  synced: number;
  remaining: number;
  online: boolean;
}> {
  if (!navigator.onLine) {
    return { synced: 0, remaining: outboxList(orgId).length, online: false };
  }
  const pending = outboxList(orgId);
  const keep: OutboxEntry[] = [];
  let synced = 0;
  for (const entry of pending) {
    try {
      await apiMutator<unknown>(entry.path, {
        method: entry.method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(entry.body),
      });
      synced += 1;
    } catch (error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        // Rechazo de contrato: no reencolar — el servidor ya dijo que no.
        synced += 1;
        continue;
      }
      keep.push(entry);
      keep.push(...pending.slice(pending.indexOf(entry) + 1));
      break;
    }
  }
  outboxSave(orgId, keep);
  return { synced, remaining: keep.length, online: true };
}
