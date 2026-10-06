/** P12 — forma de `production_station_queue` y derivados compartidos entre
 * el tablero del jefe y la vista del operario. El endpoint devuelve dicts
 * abiertos; estos tipos son la proyección que la UI consume. */

export type StationQueueEntry = {
  step_id?: string;
  order_id?: string;
  order_code?: string;
  sequence?: number;
  label?: string;
  status?: string;
  note?: string | null;
  work_center_code?: string;
  work_center_name?: string;
  /** True solo en el primer paso abierto de cada OT — la tarjeta "Siguiente". */
  is_next?: boolean;
};

export type StationQueueGroup = {
  code?: string;
  label?: string;
  pending?: number;
  in_progress?: number;
  blocked?: number;
  entries?: StationQueueEntry[];
};

/** order_id → estación donde está el primer paso abierto de la OT. */
export function stationByOrder(queue: StationQueueGroup[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const group of queue) {
    for (const entry of group.entries ?? []) {
      if (entry.is_next && entry.order_id && group.code) {
        map.set(entry.order_id, String(group.code));
      }
    }
  }
  return map;
}

/** Pasos abiertos (pendientes/en curso/bloqueados) de una estación. */
export function stationEntries(group: StationQueueGroup | undefined): StationQueueEntry[] {
  return (group?.entries ?? []).slice();
}
