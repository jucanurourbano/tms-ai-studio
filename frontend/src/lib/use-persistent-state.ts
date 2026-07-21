"use client";

import { useCallback, useRef, useSyncExternalStore } from "react";

// Suscriptores por clave para notificar cambios dentro de la misma pestaña
// (el evento `storage` nativo solo cruza pestañas).
const listeners = new Map<string, Set<() => void>>();

function emit(key: string) {
  listeners.get(key)?.forEach((l) => l());
}

// Cache de snapshots por clave: mantiene una referencia estable mientras el
// contenido de localStorage no cambie (requisito de useSyncExternalStore).
const snapshotCache = new Map<string, { raw: string | null; value: unknown }>();

/**
 * Estado persistido en localStorage vía useSyncExternalStore: sin efectos ni
 * desajustes de hidratación (el servidor usa ``initial`` y el cliente actualiza
 * tras montar). API tipo useState: ``[value, setValue]``.
 */
export function usePersistentState<T>(
  key: string,
  initial: T,
): readonly [T, (next: React.SetStateAction<T>) => void] {
  const initialRef = useRef(initial);

  const subscribe = useCallback(
    (cb: () => void) => {
      let set = listeners.get(key);
      if (!set) {
        set = new Set();
        listeners.set(key, set);
      }
      set.add(cb);
      const onStorage = (e: StorageEvent) => {
        if (e.key === key) {
          snapshotCache.delete(key);
          cb();
        }
      };
      window.addEventListener("storage", onStorage);
      return () => {
        set?.delete(cb);
        window.removeEventListener("storage", onStorage);
      };
    },
    [key],
  );

  const getSnapshot = useCallback((): T => {
    let raw: string | null = null;
    try {
      raw = window.localStorage.getItem(key);
    } catch {
      /* localStorage no disponible */
    }
    const cached = snapshotCache.get(key);
    if (cached && cached.raw === raw) return cached.value as T;
    let value = initialRef.current;
    if (raw != null) {
      try {
        value = JSON.parse(raw) as T;
      } catch {
        value = initialRef.current;
      }
    }
    snapshotCache.set(key, { raw, value });
    return value;
  }, [key]);

  const getServerSnapshot = useCallback(() => initialRef.current, []);

  const value = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setValue = useCallback(
    (next: React.SetStateAction<T>) => {
      const prev = getSnapshot();
      const resolved =
        typeof next === "function" ? (next as (p: T) => T)(prev) : next;
      try {
        window.localStorage.setItem(key, JSON.stringify(resolved));
      } catch {
        /* localStorage no disponible */
      }
      snapshotCache.delete(key);
      emit(key);
    },
    [key, getSnapshot],
  );

  return [value, setValue] as const;
}
